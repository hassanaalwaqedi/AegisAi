"""
AegisAI - Cloud API Client

Asynchronous HTTP client for sending suspicious events from the edge
to the AWS GPU cloud for deep multi-model analysis.

Features:
- Non-blocking async event sending (edge never waits for cloud)
- Background worker thread consuming event queue
- Retry with exponential backoff
- Circuit breaker pattern (stops sending if cloud is consistently down)
- JPEG frame compression for bandwidth efficiency
- Thread-safe event queue

Phase 6: Edge/Cloud Hybrid Intelligence
"""

import base64
import json
import logging
import threading
import time
from collections import deque
from queue import Queue, Empty
from typing import Callable, Dict, List, Optional

from config import CloudConfig, AegisConfig
from aegis.edge.event_types import SuspiciousEvent
from aegis.cloud.cloud_types import CloudVerdict

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """
    Circuit breaker pattern for cloud API resilience.
    
    States:
    - CLOSED: Normal operation, requests go through
    - OPEN: Too many failures, requests are blocked
    - HALF_OPEN: Testing if cloud is back (allows one request)
    """
    
    def __init__(self, failure_threshold: int = 5, reset_timeout: float = 60.0):
        self._failure_count = 0
        self._failure_threshold = failure_threshold
        self._reset_timeout = reset_timeout
        self._last_failure_time = 0.0
        self._state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self._lock = threading.Lock()
    
    @property
    def state(self) -> str:
        with self._lock:
            if self._state == "OPEN":
                # Check if enough time has passed to try again
                if time.time() - self._last_failure_time >= self._reset_timeout:
                    self._state = "HALF_OPEN"
            return self._state
    
    @property
    def is_open(self) -> bool:
        return self.state == "OPEN"
    
    def record_success(self):
        with self._lock:
            self._failure_count = 0
            self._state = "CLOSED"
    
    def record_failure(self):
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._failure_count >= self._failure_threshold:
                self._state = "OPEN"
                logger.warning(
                    f"Circuit breaker OPEN after {self._failure_count} failures. "
                    f"Will retry in {self._reset_timeout}s"
                )


class CloudClient:
    """
    Async client for sending suspicious events to the cloud API.
    
    Runs a background worker thread that consumes events from a queue
    and sends them to the cloud. Edge pipeline never blocks waiting
    for cloud responses.
    
    Example:
        >>> client = CloudClient(config)
        >>> client.start()
        >>> 
        >>> # From edge pipeline (non-blocking):
        >>> client.enqueue_event(suspicious_event)
        >>> 
        >>> # Check for cloud verdicts:
        >>> verdict = client.get_latest_verdict(event_id)
        >>> 
        >>> client.stop()
    """
    
    def __init__(
        self,
        config: Optional[AegisConfig] = None,
        cloud_config: Optional[CloudConfig] = None,
        on_verdict: Optional[Callable[[CloudVerdict], None]] = None,
    ):
        """
        Initialize the cloud client.
        
        Args:
            config: Full AegisConfig instance (preferred)
            cloud_config: CloudConfig instance (alternative)
            on_verdict: Callback when cloud returns a verdict
        """
        if config is not None:
            self._config = config.cloud
        else:
            self._config = cloud_config or CloudConfig()
        
        self._on_verdict = on_verdict
        
        # Event queue (thread-safe)
        self._event_queue: Queue = Queue(maxsize=self._config.max_queue_size)
        
        # Verdict cache: event_id → CloudVerdict
        self._verdicts: Dict[str, CloudVerdict] = {}
        self._verdicts_lock = threading.Lock()
        self._max_verdicts_cache = 100
        
        # Circuit breaker
        self._circuit = CircuitBreaker(
            failure_threshold=self._config.circuit_breaker_failures,
            reset_timeout=self._config.circuit_breaker_reset_seconds,
        )
        
        # Worker thread
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        
        # Statistics
        self._stats = {
            "events_sent": 0,
            "events_dropped": 0,
            "events_failed": 0,
            "verdicts_received": 0,
            "avg_latency_ms": 0.0,
        }
        self._stats_lock = threading.Lock()
        
        logger.info(
            f"CloudClient initialized | "
            f"enabled={self._config.enabled}, "
            f"url={self._config.api_url or '(not configured)'}"
        )
    
    @property
    def is_enabled(self) -> bool:
        """Check if cloud communication is configured and enabled."""
        return self._config.enabled and bool(self._config.api_url)
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    @property
    def queue_size(self) -> int:
        return self._event_queue.qsize()
    
    @property
    def circuit_state(self) -> str:
        return self._circuit.state
    
    def start(self):
        """Start the background worker thread."""
        if not self.is_enabled:
            logger.info("CloudClient not enabled — skipping start")
            return
        
        if self._running:
            return
        
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="aegis-cloud-worker"
        )
        self._worker_thread.start()
        logger.info("CloudClient worker started")
    
    def stop(self):
        """Stop the background worker thread."""
        if not self._running:
            return
        
        self._running = False
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=3.0)
        logger.info("CloudClient worker stopped")
    
    def enqueue_event(self, event: SuspiciousEvent) -> bool:
        """
        Add a suspicious event to the send queue (non-blocking).
        
        Args:
            event: SuspiciousEvent to send to cloud
            
        Returns:
            True if queued, False if dropped (queue full or disabled)
        """
        if not self.is_enabled:
            return False
        
        if self._circuit.is_open:
            logger.debug("Circuit breaker open — dropping event")
            with self._stats_lock:
                self._stats["events_dropped"] += 1
            return False
        
        try:
            self._event_queue.put_nowait(event)
            return True
        except Exception:
            logger.debug("Event queue full — dropping oldest")
            with self._stats_lock:
                self._stats["events_dropped"] += 1
            return False
    
    def get_verdict(self, event_id: str) -> Optional[CloudVerdict]:
        """Get a cached cloud verdict by event ID."""
        with self._verdicts_lock:
            return self._verdicts.get(event_id)
    
    def get_latest_verdicts(self, count: int = 10) -> List[CloudVerdict]:
        """Get most recent cloud verdicts."""
        with self._verdicts_lock:
            items = list(self._verdicts.values())
            return items[-count:]
    
    def _worker_loop(self):
        """Background loop: consume queue and send to cloud."""
        logger.info("Cloud worker loop started")
        
        while self._running:
            try:
                event = self._event_queue.get(timeout=1.0)
            except Empty:
                continue
            
            # Send to cloud with retry
            verdict = self._send_with_retry(event)
            
            if verdict:
                # Cache verdict
                with self._verdicts_lock:
                    self._verdicts[verdict.event_id] = verdict
                    # Trim cache
                    if len(self._verdicts) > self._max_verdicts_cache:
                        oldest = next(iter(self._verdicts))
                        del self._verdicts[oldest]
                
                # Callback
                if self._on_verdict:
                    try:
                        self._on_verdict(verdict)
                    except Exception as e:
                        logger.error(f"Verdict callback error: {e}")
                
                with self._stats_lock:
                    self._stats["verdicts_received"] += 1
        
        logger.info("Cloud worker loop stopped")
    
    def _send_with_retry(self, event: SuspiciousEvent) -> Optional[CloudVerdict]:
        """
        Send event to cloud API with retry and exponential backoff.
        
        Returns:
            CloudVerdict if successful, None if all retries failed
        """
        import requests  # lazy import to avoid dependency when cloud is disabled
        
        for attempt in range(self._config.max_retries):
            if self._circuit.is_open:
                return None
            
            try:
                start = time.time()
                
                # Build payload
                payload = event.to_dict()
                
                # Encode frame as base64 for JSON transport
                payload["frame_base64"] = base64.b64encode(
                    event.frame_jpeg
                ).decode('ascii')
                
                # POST to cloud
                headers = {
                    "Content-Type": "application/json",
                    "X-API-Key": self._config.api_key,
                }
                
                response = requests.post(
                    f"{self._config.api_url}/analyze",
                    json=payload,
                    headers=headers,
                    timeout=self._config.timeout_seconds,
                )
                
                elapsed_ms = (time.time() - start) * 1000
                
                if response.status_code == 200:
                    self._circuit.record_success()
                    with self._stats_lock:
                        self._stats["events_sent"] += 1
                        # Running average latency
                        n = self._stats["events_sent"]
                        self._stats["avg_latency_ms"] = (
                            self._stats["avg_latency_ms"] * (n - 1) + elapsed_ms
                        ) / n
                    
                    verdict = CloudVerdict.from_dict(response.json())
                    verdict.processing_time_ms = elapsed_ms
                    
                    logger.debug(
                        f"Cloud verdict received | "
                        f"event={event.event_id} | "
                        f"risk={verdict.risk_level} | "
                        f"latency={elapsed_ms:.0f}ms"
                    )
                    return verdict
                else:
                    logger.warning(
                        f"Cloud API error {response.status_code}: "
                        f"{response.text[:200]}"
                    )
                    self._circuit.record_failure()
                    
            except requests.exceptions.Timeout:
                logger.warning(f"Cloud API timeout (attempt {attempt + 1})")
                self._circuit.record_failure()
                
            except requests.exceptions.ConnectionError:
                logger.warning(f"Cloud API connection error (attempt {attempt + 1})")
                self._circuit.record_failure()
                
            except Exception as e:
                logger.error(f"Cloud API unexpected error: {e}")
                self._circuit.record_failure()
            
            # Exponential backoff
            if attempt < self._config.max_retries - 1:
                backoff = min(2 ** attempt * 0.5, 10.0)
                time.sleep(backoff)
        
        with self._stats_lock:
            self._stats["events_failed"] += 1
        
        return None
    
    def get_stats(self) -> dict:
        """Get client statistics."""
        with self._stats_lock:
            stats = dict(self._stats)
        
        stats["enabled"] = self.is_enabled
        stats["running"] = self._running
        stats["queue_size"] = self.queue_size
        stats["circuit_state"] = self.circuit_state
        return stats
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, *args):
        self.stop()
    
    def __repr__(self) -> str:
        return (
            f"CloudClient(enabled={self.is_enabled}, "
            f"circuit={self.circuit_state}, "
            f"queue={self.queue_size})"
        )
