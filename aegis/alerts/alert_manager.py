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
import os
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, Hashable, List, Optional, Set
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
        self._cooldowns: Dict[Hashable, datetime] = {}
        
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
        factors: Optional[List[str]] = None,
        cooldown_key: Optional[Hashable] = None,
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
        cooldown_identity = cooldown_key if cooldown_key is not None else track_id
        if not self._check_cooldown(cooldown_identity):
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
        self._update_cooldown(cooldown_identity)
        
        # Record in history
        with self._lock:
            self._alerts.append(alert)
            self._update_stats(alert)
        
        logger.debug(f"Alert generated: {alert.event_id}")
        return alert
    
    def _check_cooldown(self, track_id: Hashable) -> bool:
        """
        Check if track is past cooldown period.
        
        Args:
            track_id: Track identifier
            
        Returns:
            True if past cooldown, False if still in cooldown
        """
        with self._lock:
            if track_id not in self._cooldowns:
                return not self._has_persisted_cooldown(str(track_id))
            
            last_alert = self._cooldowns[track_id]
            cooldown = timedelta(seconds=self._config.cooldown_seconds)
            
            return datetime.now() - last_alert > cooldown
    
    def _update_cooldown(self, track_id: Hashable) -> None:
        """Update cooldown timestamp for a track."""
        with self._lock:
            self._cooldowns[track_id] = datetime.now()

    def clear_cooldowns(self, prefix: Optional[str] = None) -> None:
        """Clear all cooldowns, or only string identities for one camera."""
        with self._lock:
            if prefix is None:
                self._cooldowns.clear()
                return
            self._cooldowns = {
                key: value
                for key, value in self._cooldowns.items()
                if not str(key).startswith(prefix)
            }
    
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
        elif alert.delivery_status == "created":
            alert.delivery_status = "not_configured"
    
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
            self._api_queue.put_nowait(alert)
            alert.delivery_status = "queued"
            alert.delivery_attempts += 1
            alert.delivered_at = datetime.now()
            alert.last_delivery_error = None
        except Exception as exc:
            # The durable record captures the delivery failure; losing an alert
            # silently is not acceptable for an operator workflow.
            alert.delivery_status = "failed"
            alert.delivery_attempts += 1
            alert.last_delivery_error = f"API queue unavailable: {type(exc).__name__}"
            logger.error("Alert API queue dispatch failed event_id=%s: %s", alert.event_id, exc)
    
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

    def persist_alert(
        self,
        alert: Alert,
        *,
        event_id: str,
        cooldown_key: Optional[Hashable] = None,
    ) -> bool:
        """Persist finalized alert state after its evidence event is durable.

        Risk generation remains non-blocking for camera processing, but an
        alert is not considered durable until it has an evidence event ID. The
        record retains acknowledgement, queue delivery state, and cooldown
        metadata across process restarts.
        """
        try:
            from aegis.database.connection import get_db_session
            from aegis.database.repositories import EventRepository, OperationalAlertRepository

            cooldown_identity = str(cooldown_key if cooldown_key is not None else alert.track_id)
            cooldown_expires_at = alert.timestamp + timedelta(seconds=self._config.cooldown_seconds)
            with get_db_session() as session:
                evidence_event = EventRepository(session).get_by_event_id(str(event_id))
                if evidence_event is None:
                    raise ValueError(f"Cannot persist alert without evidence event {event_id}")
                record = OperationalAlertRepository(session).create_or_get(
                    alert_id=alert.event_id,
                    event_id=str(event_id),
                    event_record_id=evidence_event.id,
                    track_id=str(alert.track_id),
                    level=alert.level.value,
                    risk_score=float(alert.risk_score),
                    message=alert.message,
                    zone=alert.zone or None,
                    factors=list(alert.factors),
                    cooldown_key=cooldown_identity,
                    cooldown_expires_at=cooldown_expires_at,
                    delivery_status=alert.delivery_status,
                    delivery_attempts=alert.delivery_attempts,
                    delivered_at=alert.delivered_at,
                    last_delivery_error=alert.last_delivery_error,
                )
                # Preserve the public alert identity on the existing durable
                # event so evidence, incident, and alert APIs agree.
                evidence_event.alert_id = alert.event_id
                self._cooldowns[cooldown_key if cooldown_key is not None else alert.track_id] = alert.timestamp
                logger.info("Persisted alert alert_id=%s event_id=%s record_id=%s", alert.event_id, event_id, record.id)
            return True
        except Exception as exc:
            logger.error("Alert persistence failed alert_id=%s: %s", alert.event_id, exc)
            return False

    def get_persisted_alerts(
        self,
        *,
        limit: int = 50,
        level: Optional[str] = None,
        active_only: bool = False,
    ) -> List[dict]:
        """Return durable alerts; never substitute the process-local history."""
        from aegis.database.connection import get_db_session
        from aegis.database.repositories import OperationalAlertRepository

        with get_db_session() as session:
            repository = OperationalAlertRepository(session)
            records = repository.get_active(limit) if active_only else repository.get_recent(limit, level)
            if active_only and level:
                records = [record for record in records if record.level == level.upper()]
            return [record.to_dict() for record in records]

    def acknowledge_persisted_alert(self, alert_id: str, acknowledged_by: str = "api-key-operator") -> bool:
        """Acknowledge the durable record and mirror the current in-memory copy."""
        from aegis.database.connection import get_db_session
        from aegis.database.repositories import OperationalAlertRepository

        with get_db_session() as session:
            record = OperationalAlertRepository(session).acknowledge(alert_id, acknowledged_by)
            if record is None:
                return False
        with self._lock:
            for alert in self._alerts:
                if alert.event_id == alert_id:
                    alert.acknowledged = True
                    break
        return True

    def get_persisted_summary(self) -> dict:
        from aegis.database.connection import get_db_session
        from aegis.database.repositories import OperationalAlertRepository

        with get_db_session() as session:
            return OperationalAlertRepository(session).summary()

    def _has_persisted_cooldown(self, cooldown_key: str) -> bool:
        """Consult durable cooldown metadata on a cold process when configured."""
        if not cooldown_key or not os.getenv("DATABASE_URL"):
            return False
        try:
            from aegis.database.connection import get_db_session
            from aegis.database.repositories import OperationalAlertRepository

            with get_db_session() as session:
                return OperationalAlertRepository(session).active_cooldown(cooldown_key) is not None
        except Exception as exc:
            logger.warning("Could not verify persisted alert cooldown: %s", type(exc).__name__)
            return False
    
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
