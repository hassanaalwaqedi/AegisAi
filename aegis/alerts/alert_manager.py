"""
AegisAI - Smart City Risk Intelligence System
Alert Manager Module

This module handles alert generation, deduplication, and dispatch.
Prevents alert flooding with cooldown and manages multiple channels.

Features:
- Generate alerts from risk scores
- Per-track cooldown to prevent flooding
- Deduplication within cooldown period
- Multi-channel dispatch (console, file, API)
- Audit trail logging

Phase 4: Response & Productization Layer
"""

import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set
from queue import Queue

from aegis.alerts.alert_types import Alert, AlertLevel, AlertChannel, AlertSummary

# Configure module logger
logger = logging.getLogger(__name__)


@dataclass
class AlertManagerConfig:
    """
    Configuration for alert manager.
    
    Attributes:
        enabled: Whether alerting is enabled
        min_level: Minimum risk level to trigger alerts
        cooldown_seconds: Per-track cooldown period
        max_alerts_queue: Maximum alerts in API queue
        log_to_file: Whether to write to file
        log_path: Path to alert log file
        channels: Enabled alert channels
    """
    enabled: bool = True
    min_level: AlertLevel = AlertLevel.HIGH
    cooldown_seconds: float = 30.0
    max_alerts_queue: int = 100
    log_to_file: bool = True
    log_path: str = "data/output/alerts.log"
    channels: Set[AlertChannel] = field(default_factory=lambda: {
        AlertChannel.CONSOLE,
        AlertChannel.FILE,
        AlertChannel.API
    })


class AlertManager:
    """
    Manages alert generation, deduplication, and dispatch.
    
    Tracks cooldowns per track ID to prevent alert flooding.
    Dispatches to multiple channels (console, file, API queue).
    
    Attributes:
        config: Alert manager configuration
        
    Example:
        >>> manager = AlertManager()
        >>> alert = manager.process_risk(risk_score)
        >>> if alert:
        ...     print(f"Alert generated: {alert.message}")
    """
    
    def __init__(self, config: Optional[AlertManagerConfig] = None):
        """
        Initialize the alert manager.
        
        Args:
            config: Alert manager configuration
        """
        self._config = config or AlertManagerConfig()
        
        # Cooldown tracking: track_id -> last_alert_time
        self._cooldowns: Dict[int, datetime] = {}
        
        # Alert history
        self._alerts: deque = deque(maxlen=1000)
        
        # API event queue (thread-safe)
        self._api_queue: Queue = Queue(maxsize=self._config.max_alerts_queue)
        
        # Statistics
        self._stats = AlertSummary(start_time=datetime.now())
        
        # Thread lock for thread-safe operations
        self._lock = threading.Lock()
        
        # Ensure log directory exists
        if self._config.log_to_file:
            log_path = Path(self._config.log_path)
            log_path.parent.mkdir(parents=True, exist_ok=True)
        
        logger.info(
            f"AlertManager initialized with "
            f"min_level={self._config.min_level.value}, "
            f"cooldown={self._config.cooldown_seconds}s"
        )
    
    @property
    def config(self) -> AlertManagerConfig:
        """Get the manager configuration."""
        return self._config
    
    @property
    def alert_count(self) -> int:
        """Get total alerts generated."""
        return self._stats.total_alerts
    
    @property
    def api_queue(self) -> Queue:
        """Get the API event queue."""
        return self._api_queue
    
    def process_risk(
        self,
        track_id: int,
        risk_level: str,
        risk_score: float,
        message: str,
        zone: str = "",
        factors: Optional[List[str]] = None
    ) -> Optional[Alert]:
        """
        Process a risk score and generate alert if warranted.
        
        Args:
            track_id: Track identifier
            risk_level: Risk level string (LOW, MEDIUM, HIGH, CRITICAL)
            risk_score: Numerical risk score (0-1)
            message: Alert message
            zone: Zone name
            factors: Contributing factors
            
        Returns:
            Alert if generated, None if suppressed
        """
        if not self._config.enabled:
            return None
        
        # Map risk level to alert level
        alert_level = AlertLevel.from_risk_level(risk_level)
        
        # Check if meets minimum level
        if alert_level.priority < self._config.min_level.priority:
            return None
        
        # Check cooldown
        if not self._check_cooldown(track_id):
            return None
        
        # Generate alert
        alert = Alert(
            event_id=Alert.generate_id(),
            track_id=track_id,
            level=alert_level,
            risk_score=risk_score,
            message=message,
            zone=zone,
            factors=factors or [],
            timestamp=datetime.now()
        )
        
        # Dispatch to channels
        self._dispatch(alert)
        
        # Update cooldown
        self._update_cooldown(track_id)
        
        # Record in history
        with self._lock:
            self._alerts.append(alert)
            self._update_stats(alert)
        
        logger.debug(f"Alert generated: {alert.event_id}")
        return alert
    
    def _check_cooldown(self, track_id: int) -> bool:
        """
        Check if track is past cooldown period.
        
        Args:
            track_id: Track identifier
            
        Returns:
            True if past cooldown, False if still in cooldown
        """
        with self._lock:
            if track_id not in self._cooldowns:
                return True
            
            last_alert = self._cooldowns[track_id]
            cooldown = timedelta(seconds=self._config.cooldown_seconds)
            
            return datetime.now() - last_alert > cooldown
    
    def _update_cooldown(self, track_id: int) -> None:
        """Update cooldown timestamp for a track."""
        with self._lock:
            self._cooldowns[track_id] = datetime.now()
    
    def _dispatch(self, alert: Alert) -> None:
        """
        Dispatch alert to configured channels.
        
        Args:
            alert: Alert to dispatch
        """
        if AlertChannel.CONSOLE in self._config.channels:
            self._dispatch_console(alert)
        
        if AlertChannel.FILE in self._config.channels:
            self._dispatch_file(alert)
        
        if AlertChannel.API in self._config.channels:
            self._dispatch_api(alert)
    
    def _dispatch_console(self, alert: Alert) -> None:
        """Print alert to console."""
        print(alert.to_console_string())
    
    def _dispatch_file(self, alert: Alert) -> None:
        """Write alert to log file."""
        try:
            with open(self._config.log_path, "a", encoding="utf-8") as f:
                f.write(alert.to_log_string() + "\n")
        except Exception as e:
            logger.error(f"Failed to write alert to file: {e}")
    
    def _dispatch_api(self, alert: Alert) -> None:
        """Add alert to API queue."""
        try:
            # Non-blocking put, drop if queue is full
            self._api_queue.put_nowait(alert)
        except Exception:
            # Queue full, silently drop oldest if needed
            pass
    
    def _update_stats(self, alert: Alert) -> None:
        """Update statistics with new alert."""
        self._stats.total_alerts += 1
        self._stats.by_level[alert.level.value] += 1
        self._stats.end_time = datetime.now()
        
        # Keep recent alerts
        if len(self._stats.recent_alerts) >= 10:
            self._stats.recent_alerts.pop(0)
        self._stats.recent_alerts.append(alert)
    
    def get_recent_alerts(self, count: int = 10) -> List[Alert]:
        """
        Get most recent alerts.
        
        Args:
            count: Number of alerts to return
            
        Returns:
            List of recent alerts
        """
        with self._lock:
            return list(self._alerts)[-count:]
    
    def get_summary(self) -> AlertSummary:
        """
        Get alert summary statistics.
        
        Returns:
            AlertSummary with counts and recent alerts
        """
        with self._lock:
            self._stats.end_time = datetime.now()
            return self._stats
    
    def get_alerts_for_api(self, limit: int = 20) -> List[dict]:
        """
        Get alerts from API queue as dictionaries.
        
        Args:
            limit: Maximum alerts to return
            
        Returns:
            List of alert dictionaries
        """
        alerts = []
        while len(alerts) < limit and not self._api_queue.empty():
            try:
                alert = self._api_queue.get_nowait()
                alerts.append(alert.to_dict())
            except Exception:
                break
        return alerts
    
    def cleanup_cooldowns(self) -> int:
        """
        Remove expired cooldown entries.
        
        Returns:
            Number of entries removed
        """
        with self._lock:
            now = datetime.now()
            cooldown = timedelta(seconds=self._config.cooldown_seconds * 2)
            
            expired = [
                tid for tid, time in self._cooldowns.items()
                if now - time > cooldown
            ]
            
            for tid in expired:
                del self._cooldowns[tid]
            
            return len(expired)
    
    def reset(self) -> None:
        """Reset manager state."""
        with self._lock:
            self._cooldowns.clear()
            self._alerts.clear()
            self._stats = AlertSummary(start_time=datetime.now())
            
            # Clear queue
            while not self._api_queue.empty():
                try:
                    self._api_queue.get_nowait()
                except Exception:
                    break
        
        logger.info("AlertManager reset")
    
    def __repr__(self) -> str:
        return (
            f"AlertManager(alerts={self.alert_count}, "
            f"min_level={self._config.min_level.value})"
        )
