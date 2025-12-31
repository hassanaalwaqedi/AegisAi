"""
AegisAI - Safety Rules Checker

Monitors compliance with safety and operational rules.

Features:
- Restricted zone monitoring
- Hygiene area compliance
- PPE detection (placeholder for future ML)
- Safety alert generation

Copyright 2024 AegisAI Project
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set
from datetime import datetime, timedelta
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class RuleType(Enum):
    """Types of safety rules."""
    RESTRICTED_ZONE = "restricted_zone"
    REQUIRED_ZONE = "required_zone"
    TIME_LIMIT = "time_limit"
    STAFF_ONLY = "staff_only"
    NO_ENTRY = "no_entry"


class AlertSeverity(Enum):
    """Safety alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    VIOLATION = "violation"
    CRITICAL = "critical"


@dataclass
class SafetyZone:
    """A zone with safety rules."""
    zone_id: str
    name: str
    polygon: List[Tuple[int, int]]
    rule_type: RuleType
    max_time_seconds: Optional[float] = None  # For TIME_LIMIT
    allowed_classes: Set[str] = field(default_factory=lambda: {"person"})
    alert_severity: AlertSeverity = AlertSeverity.WARNING


@dataclass
class SafetyAlert:
    """A safety rule violation alert."""
    alert_id: str
    zone_id: str
    zone_name: str
    track_id: int
    rule_type: RuleType
    severity: AlertSeverity
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    acknowledged: bool = False


class SafetyRulesChecker:
    """
    Checks safety rule compliance based on track positions.
    
    Example:
        >>> checker = SafetyRulesChecker()
        >>> checker.add_zone(SafetyZone("kitchen", "Kitchen", [...], RuleType.STAFF_ONLY))
        >>> alerts = checker.check_track(track_id=5, position=(100, 100), is_staff=False)
    """
    
    def __init__(self, alert_cooldown_seconds: float = 30.0):
        """
        Initialize safety rules checker.
        
        Args:
            alert_cooldown_seconds: Minimum time between alerts for same track/zone
        """
        self._zones: Dict[str, SafetyZone] = {}
        self._alerts: List[SafetyAlert] = []
        self._alert_cooldown = alert_cooldown_seconds
        
        # Track time in zones
        self._zone_entry_times: Dict[Tuple[int, str], datetime] = {}
        
        # Alert deduplication
        self._last_alerts: Dict[Tuple[int, str], datetime] = {}
        
        self._alert_counter = 0
        
        logger.info("SafetyRulesChecker initialized")
    
    def add_zone(self, zone: SafetyZone) -> None:
        """Add a safety zone."""
        self._zones[zone.zone_id] = zone
        logger.debug(f"Added safety zone: {zone.name} ({zone.rule_type.value})")
    
    def check_track(
        self,
        track_id: int,
        position: Tuple[int, int],
        class_name: str = "person",
        is_staff: bool = False
    ) -> List[SafetyAlert]:
        """
        Check if a track violates any safety rules.
        
        Args:
            track_id: Track identifier
            position: Current position (x, y)
            class_name: Object class
            is_staff: Whether this is a staff member
            
        Returns:
            List of safety alerts generated
        """
        alerts = []
        now = datetime.now()
        
        for zone_id, zone in self._zones.items():
            in_zone = self._point_in_polygon(position, zone.polygon)
            zone_key = (track_id, zone_id)
            
            if in_zone:
                # Track zone entry time
                if zone_key not in self._zone_entry_times:
                    self._zone_entry_times[zone_key] = now
                
                # Check rules
                alert = self._check_zone_rules(
                    track_id, zone, class_name, is_staff, now
                )
                if alert:
                    alerts.append(alert)
            else:
                # Left zone - clear entry time
                if zone_key in self._zone_entry_times:
                    del self._zone_entry_times[zone_key]
        
        return alerts
    
    def _check_zone_rules(
        self,
        track_id: int,
        zone: SafetyZone,
        class_name: str,
        is_staff: bool,
        now: datetime
    ) -> Optional[SafetyAlert]:
        """Check rules for a specific zone."""
        zone_key = (track_id, zone.zone_id)
        
        # Check cooldown
        if zone_key in self._last_alerts:
            if (now - self._last_alerts[zone_key]).total_seconds() < self._alert_cooldown:
                return None
        
        alert = None
        
        if zone.rule_type == RuleType.NO_ENTRY:
            alert = self._create_alert(
                zone, track_id,
                f"Unauthorized entry in {zone.name}",
                AlertSeverity.CRITICAL
            )
        
        elif zone.rule_type == RuleType.STAFF_ONLY and not is_staff:
            alert = self._create_alert(
                zone, track_id,
                f"Non-staff person in staff-only zone: {zone.name}",
                AlertSeverity.WARNING
            )
        
        elif zone.rule_type == RuleType.TIME_LIMIT and zone.max_time_seconds:
            entry_time = self._zone_entry_times.get(zone_key, now)
            time_in_zone = (now - entry_time).total_seconds()
            
            if time_in_zone > zone.max_time_seconds:
                alert = self._create_alert(
                    zone, track_id,
                    f"Time limit exceeded in {zone.name} ({time_in_zone:.0f}s > {zone.max_time_seconds}s)",
                    zone.alert_severity
                )
        
        elif zone.rule_type == RuleType.RESTRICTED_ZONE:
            if class_name.lower() not in {c.lower() for c in zone.allowed_classes}:
                alert = self._create_alert(
                    zone, track_id,
                    f"Restricted zone violation: {class_name} in {zone.name}",
                    zone.alert_severity
                )
        
        if alert:
            self._last_alerts[zone_key] = now
            self._alerts.append(alert)
        
        return alert
    
    def _create_alert(
        self,
        zone: SafetyZone,
        track_id: int,
        message: str,
        severity: AlertSeverity
    ) -> SafetyAlert:
        """Create a new safety alert."""
        self._alert_counter += 1
        
        return SafetyAlert(
            alert_id=f"safety_{self._alert_counter}",
            zone_id=zone.zone_id,
            zone_name=zone.name,
            track_id=track_id,
            rule_type=zone.rule_type,
            severity=severity,
            message=message
        )
    
    def _point_in_polygon(self, point: Tuple[int, int], polygon: List[Tuple[int, int]]) -> bool:
        """Ray casting point-in-polygon test."""
        x, y = point
        n = len(polygon)
        inside = False
        p1x, p1y = polygon[0]
        for i in range(1, n + 1):
            p2x, p2y = polygon[i % n]
            if y > min(p1y, p2y) and y <= max(p1y, p2y) and x <= max(p1x, p2x):
                if p1y != p2y:
                    xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                if p1x == p2x or x <= xinters:
                    inside = not inside
            p1x, p1y = p2x, p2y
        return inside
    
    def get_active_alerts(self, since_minutes: int = 60) -> List[SafetyAlert]:
        """Get alerts from the last N minutes."""
        cutoff = datetime.now() - timedelta(minutes=since_minutes)
        return [a for a in self._alerts if a.timestamp > cutoff]
    
    def get_unacknowledged_alerts(self) -> List[SafetyAlert]:
        """Get alerts that haven't been acknowledged."""
        return [a for a in self._alerts if not a.acknowledged]
    
    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert."""
        for alert in self._alerts:
            if alert.alert_id == alert_id:
                alert.acknowledged = True
                return True
        return False
    
    def get_metrics(self) -> Dict:
        """Get safety metrics."""
        recent = self.get_active_alerts(60)
        
        by_severity = {s.value: 0 for s in AlertSeverity}
        for alert in recent:
            by_severity[alert.severity.value] += 1
        
        return {
            "total_zones": len(self._zones),
            "total_alerts": len(self._alerts),
            "alerts_last_hour": len(recent),
            "unacknowledged": len(self.get_unacknowledged_alerts()),
            "by_severity": by_severity,
            "recent_alerts": [
                {
                    "id": a.alert_id,
                    "zone": a.zone_name,
                    "message": a.message,
                    "severity": a.severity.value,
                    "timestamp": a.timestamp.isoformat()
                }
                for a in recent[-10:]  # Last 10
            ]
        }
