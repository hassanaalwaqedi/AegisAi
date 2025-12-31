"""
AegisAI - Production RTSP Video Source

Resilient RTSP video source with auto-reconnect, health monitoring,
and secure credential handling.

Features:
- Auto-reconnect with exponential backoff
- Configurable timeouts
- Health status reporting (UP/DEGRADED/DOWN)
- Thread-safe frame buffer
- Credential masking in logs

Copyright 2024 AegisAI Project
"""

import logging
import threading
import time
from enum import Enum
from typing import Optional, Tuple, Callable, Iterator
from collections import deque
from dataclasses import dataclass
from datetime import datetime

import cv2
import numpy as np

from aegis.utils.credentials import mask_rtsp_url, get_secure_logger

# Use secure logger that masks credentials
logger = get_secure_logger(__name__)


class CameraHealth(Enum):
    """Camera connection health status."""
    UP = "up"           # Connected and receiving frames
    DEGRADED = "degraded"  # Experiencing issues but still working
    DOWN = "down"       # Not connected or not receiving frames
    UNKNOWN = "unknown"  # Initial state before first connection


@dataclass
class CameraStats:
    """Camera statistics and metrics."""
    health: CameraHealth
    fps: float
    latency_ms: float
    frames_received: int
    frames_dropped: int
    reconnect_count: int
    last_frame_time: Optional[datetime]
    connected_since: Optional[datetime]
    error_message: Optional[str]
    
    def to_dict(self) -> dict:
        return {
            "health": self.health.value,
            "fps": round(self.fps, 2),
            "latency_ms": round(self.latency_ms, 2),
            "frames_received": self.frames_received,
            "frames_dropped": self.frames_dropped,
            "reconnect_count": self.reconnect_count,
            "last_frame_time": self.last_frame_time.isoformat() if self.last_frame_time else None,
            "connected_since": self.connected_since.isoformat() if self.connected_since else None,
            "error_message": self.error_message,
        }


class RTSPSource:
    """
    Production-grade RTSP video source with resilience features.
    
    Provides automatic reconnection, health monitoring, and thread-safe
    frame buffering for robust IP camera integration.
    
    Attributes:
        camera_id: Unique identifier for this camera
        url: RTSP URL (credentials masked in logs)
        health: Current connection health status
        
    Example:
        >>> source = RTSPSource("cam1", "rtsp://admin:pass@192.168.1.100/stream")
        >>> source.start()
        >>> for frame in source:
        ...     process(frame)
        >>> source.stop()
    """
    
    def __init__(
        self,
        camera_id: str,
        url: str,
        connection_timeout: float = 5.0,
        max_retries: int = 10,
        retry_base_delay: float = 1.0,
        retry_max_delay: float = 60.0,
        buffer_size: int = 5,
        health_check_interval: float = 5.0,
        on_health_change: Optional[Callable[[str, CameraHealth], None]] = None,
        on_frame: Optional[Callable[[str, np.ndarray], None]] = None,
    ):
        """
        Initialize RTSP source.
        
        Args:
            camera_id: Unique identifier for this camera
            url: RTSP URL with optional credentials
            connection_timeout: Timeout for connection attempts (seconds)
            max_retries: Maximum reconnection attempts (0 = infinite)
            retry_base_delay: Initial delay between retries (seconds)
            retry_max_delay: Maximum delay between retries (seconds)
            buffer_size: Frame buffer size
            health_check_interval: Interval for health checks (seconds)
            on_health_change: Callback when health status changes
            on_frame: Callback when frame received
        """
        self.camera_id = camera_id
        self._url = url
        self._masked_url = mask_rtsp_url(url)
        
        # Configuration
        self._connection_timeout = connection_timeout
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay
        self._retry_max_delay = retry_max_delay
        self._buffer_size = buffer_size
        self._health_check_interval = health_check_interval
        
        # Callbacks
        self._on_health_change = on_health_change
        self._on_frame = on_frame
        
        # State
        self._capture: Optional[cv2.VideoCapture] = None
        self._health = CameraHealth.UNKNOWN
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._health_thread: Optional[threading.Thread] = None
        
        # Thread-safe frame buffer
        self._frame_buffer: deque = deque(maxlen=buffer_size)
        self._buffer_lock = threading.Lock()
        self._frame_available = threading.Event()
        
        # Statistics
        self._frames_received = 0
        self._frames_dropped = 0
        self._reconnect_count = 0
        self._last_frame_time: Optional[datetime] = None
        self._connected_since: Optional[datetime] = None
        self._error_message: Optional[str] = None
        self._fps_samples: deque = deque(maxlen=30)
        self._latency_samples: deque = deque(maxlen=30)
        
        logger.info(f"RTSPSource created: {camera_id} -> {self._masked_url}")
    
    @property
    def health(self) -> CameraHealth:
        """Get current health status."""
        return self._health
    
    @property
    def url(self) -> str:
        """Get masked URL (safe for logging)."""
        return self._masked_url
    
    def get_stats(self) -> CameraStats:
        """Get current camera statistics."""
        avg_fps = sum(self._fps_samples) / len(self._fps_samples) if self._fps_samples else 0.0
        avg_latency = sum(self._latency_samples) / len(self._latency_samples) if self._latency_samples else 0.0
        
        return CameraStats(
            health=self._health,
            fps=avg_fps,
            latency_ms=avg_latency,
            frames_received=self._frames_received,
            frames_dropped=self._frames_dropped,
            reconnect_count=self._reconnect_count,
            last_frame_time=self._last_frame_time,
            connected_since=self._connected_since,
            error_message=self._error_message,
        )
    
    def _set_health(self, health: CameraHealth, error: Optional[str] = None):
        """Update health status and trigger callback."""
        if health != self._health:
            old_health = self._health
            self._health = health
            self._error_message = error
            
            logger.info(f"Camera {self.camera_id} health: {old_health.value} -> {health.value}")
            
            if self._on_health_change:
                try:
                    self._on_health_change(self.camera_id, health)
                except Exception as e:
                    logger.error(f"Health callback error: {e}")
    
    def _connect(self) -> bool:
        """Attempt to connect to RTSP stream."""
        logger.info(f"Connecting to {self._masked_url}")
        
        try:
            # Configure OpenCV for RTSP
            self._capture = cv2.VideoCapture(self._url, cv2.CAP_FFMPEG)
            
            # Set timeout properties
            self._capture.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, self._connection_timeout * 1000)
            self._capture.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, self._connection_timeout * 1000)
            
            # Set buffer size to reduce latency
            self._capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            if not self._capture.isOpened():
                raise ConnectionError("Failed to open RTSP stream")
            
            # Test read
            ret, _ = self._capture.read()
            if not ret:
                raise ConnectionError("Failed to read initial frame")
            
            self._connected_since = datetime.utcnow()
            self._set_health(CameraHealth.UP)
            logger.info(f"Connected to camera {self.camera_id}")
            return True
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Connection failed for {self.camera_id}: {error_msg}")
            self._set_health(CameraHealth.DOWN, error_msg)
            self._release_capture()
            return False
    
    def _release_capture(self):
        """Release video capture resources."""
        if self._capture is not None:
            try:
                self._capture.release()
            except:
                pass
            self._capture = None
    
    def _reconnect_with_backoff(self) -> bool:
        """Attempt reconnection with exponential backoff."""
        attempt = 0
        delay = self._retry_base_delay
        
        while self._running:
            attempt += 1
            self._reconnect_count += 1
            
            if self._max_retries > 0 and attempt > self._max_retries:
                logger.error(f"Max retries ({self._max_retries}) exceeded for {self.camera_id}")
                self._set_health(CameraHealth.DOWN, "Max retries exceeded")
                return False
            
            logger.info(f"Reconnect attempt {attempt} for {self.camera_id} (delay: {delay:.1f}s)")
            
            if self._connect():
                return True
            
            # Exponential backoff
            time.sleep(delay)
            delay = min(delay * 2, self._retry_max_delay)
        
        return False
    
    def _capture_loop(self):
        """Main capture loop running in separate thread."""
        consecutive_failures = 0
        max_consecutive_failures = 5
        
        while self._running:
            if self._capture is None or not self._capture.isOpened():
                if not self._reconnect_with_backoff():
                    break
                consecutive_failures = 0
                continue
            
            try:
                start_time = time.time()
                ret, frame = self._capture.read()
                latency = (time.time() - start_time) * 1000
                
                if not ret or frame is None:
                    consecutive_failures += 1
                    self._frames_dropped += 1
                    
                    if consecutive_failures >= max_consecutive_failures:
                        logger.warning(f"Multiple frame failures for {self.camera_id}, reconnecting...")
                        self._set_health(CameraHealth.DEGRADED, "Frame read failures")
                        self._release_capture()
                        consecutive_failures = 0
                    continue
                
                consecutive_failures = 0
                self._frames_received += 1
                self._last_frame_time = datetime.utcnow()
                
                # Update metrics
                if self._fps_samples:
                    last_time = self._fps_samples[-1][1] if isinstance(self._fps_samples[-1], tuple) else time.time() - 0.033
                    fps = 1.0 / max(time.time() - last_time, 0.001)
                    self._fps_samples.append((fps, time.time()))
                else:
                    self._fps_samples.append((30.0, time.time()))
                
                self._latency_samples.append(latency)
                
                # Add to buffer
                with self._buffer_lock:
                    self._frame_buffer.append(frame)
                    self._frame_available.set()
                
                # Callback
                if self._on_frame:
                    try:
                        self._on_frame(self.camera_id, frame)
                    except Exception as e:
                        logger.error(f"Frame callback error: {e}")
                
            except Exception as e:
                logger.error(f"Capture error for {self.camera_id}: {e}")
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive_failures:
                    self._set_health(CameraHealth.DEGRADED, str(e))
                    self._release_capture()
                    consecutive_failures = 0
    
    def _health_check_loop(self):
        """Background health monitoring loop."""
        while self._running:
            time.sleep(self._health_check_interval)
            
            if not self._running:
                break
            
            # Check if receiving frames
            if self._last_frame_time:
                time_since_frame = (datetime.utcnow() - self._last_frame_time).total_seconds()
                
                if time_since_frame > self._health_check_interval * 2:
                    self._set_health(CameraHealth.DEGRADED, "No frames received")
                elif time_since_frame > self._health_check_interval * 4:
                    self._set_health(CameraHealth.DOWN, "Stream timeout")
                elif self._health == CameraHealth.DEGRADED and time_since_frame < 1.0:
                    self._set_health(CameraHealth.UP)
    
    def start(self):
        """Start the RTSP capture."""
        if self._running:
            return
        
        self._running = True
        
        # Start capture thread
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        
        # Start health check thread
        self._health_thread = threading.Thread(target=self._health_check_loop, daemon=True)
        self._health_thread.start()
        
        logger.info(f"Started RTSPSource: {self.camera_id}")
    
    def stop(self):
        """Stop the RTSP capture and release resources."""
        if not self._running:
            return
        
        logger.info(f"Stopping RTSPSource: {self.camera_id}")
        
        self._running = False
        self._frame_available.set()  # Wake up any waiting threads
        
        # Wait for threads
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        
        if self._health_thread and self._health_thread.is_alive():
            self._health_thread.join(timeout=1.0)
        
        self._release_capture()
        self._set_health(CameraHealth.DOWN, "Stopped")
        
        logger.info(f"Stopped RTSPSource: {self.camera_id}")
    
    def get_frame(self, timeout: float = 1.0) -> Optional[np.ndarray]:
        """
        Get the latest frame from buffer.
        
        Args:
            timeout: Maximum time to wait for frame
            
        Returns:
            Frame as numpy array or None if timeout/not available
        """
        if not self._running:
            return None
        
        if self._frame_available.wait(timeout):
            with self._buffer_lock:
                if self._frame_buffer:
                    return self._frame_buffer[-1]
        
        return None
    
    def __iter__(self) -> Iterator[np.ndarray]:
        """Iterate over frames."""
        while self._running:
            frame = self.get_frame(timeout=1.0)
            if frame is not None:
                yield frame
    
    def __enter__(self) -> 'RTSPSource':
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
    
    def __repr__(self) -> str:
        return f"RTSPSource(id={self.camera_id}, health={self._health.value}, url={self._masked_url})"
