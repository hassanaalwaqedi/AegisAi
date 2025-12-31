"""
AegisAI - Smart City Risk Intelligence System
Alert Module - Shared Types

This module defines all shared data structures for the Alert System.
Provides standardized containers for alerts and configurations.

Phase 4: Response & Productization Layer
"""

import uuid
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from enum import Enum
from datetime import datetime


class AlertLevel(Enum):
    """
    Alert severity levels.
    
    Attributes:
        INFO: Informational, no action needed
        WARNING: Potential concern, monitoring recommended
        HIGH: Significant risk, alert recommended
        CRITICAL: Immediate attention required
    """
    INFO = "INFO"
    WARNING = "WARNING"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    
    @classmethod
    def from_risk_level(cls, risk_level: str) -> 'AlertLevel':
        """Map risk level string to alert level."""
        mapping = {
            "LOW": cls.INFO,
            "MEDIUM": cls.WARNING,
            "HIGH": cls.HIGH,
            "CRITICAL": cls.CRITICAL
        }
        return mapping.get(risk_level, cls.INFO)
    
    @property
    def priority(self) -> int:
        """Get numeric priority (higher = more urgent)."""
        priorities = {
            AlertLevel.INFO: 1,
            AlertLevel.WARNING: 2,
            AlertLevel.HIGH: 3,
            AlertLevel.CRITICAL: 4
        }
        return priorities.get(self, 0)
    
    @property
    def color_hex(self) -> str:
        """Get hex color for display."""
        colors = {
            AlertLevel.INFO: "#4CAF50",      # Green
            AlertLevel.WARNING: "#FF9800",   # Orange
            AlertLevel.HIGH: "#F44336",      # Red
            AlertLevel.CRITICAL: "#9C27B0"   # Purple
        }
        return colors.get(self, "#9E9E9E")


class AlertChannel(Enum):
    """
    Alert dispatch channels.
    
    Attributes:
        CONSOLE: Print to console
        FILE: Write to log file
        API: Add to API event queue
    """
    CONSOLE = "CONSOLE"
    FILE = "FILE"
    API = "API"


@dataclass
class Alert:
    """
    A single alert instance.
    
    Attributes:
        event_id: Unique identifier for this alert
        track_id: Associated track ID
        level: Alert severity level
        risk_score: Numerical risk score (0-1)
        message: Human-readable alert message
        zone: Zone name (if applicable)
        factors: Contributing factors
        timestamp: When alert was generated
        acknowledged: Whether alert has been acknowledged
    """
    event_id: str
    track_id: int
    level: AlertLevel
    risk_score: float
    message: str
    zone: str = ""
    factors: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    acknowledged: bool = False
    
    @classmethod
    def generate_id(cls) -> str:
        """Generate a unique event ID."""
        now = datetime.now()
        unique = uuid.uuid4().hex[:6]
        return f"evt_{now.strftime('%Y%m%d_%H%M%S')}_{unique}"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "event_id": self.event_id,
            "track_id": self.track_id,
            "risk_level": self.level.value,
            "risk_score": round(self.risk_score, 3),
            "zone": self.zone,
            "message": self.message,
            "factors": self.factors,
            "timestamp": self.timestamp.isoformat(),
            "acknowledged": self.acknowledged
        }
    
    def to_log_string(self) -> str:
        """Format for file logging."""
        return (
            f"[{self.timestamp.isoformat()}] "
            f"[{self.level.value}] "
            f"Track {self.track_id}: {self.message} "
            f"(Score: {self.risk_score:.2f})"
        )
    
    def to_console_string(self) -> str:
        """Format for console output."""
        level_icon = {
            AlertLevel.INFO: "ℹ️",
            AlertLevel.WARNING: "⚠️",
            AlertLevel.HIGH: "🔴",
            AlertLevel.CRITICAL: "🚨"
        }.get(self.level, "•")
        
        return (
            f"{level_icon} [{self.level.value}] "
            f"Track {self.track_id}: {self.message}"
        )


@dataclass
class AlertSummary:
    """
    Summary of alerts over a time period.
    
    Attributes:
        total_alerts: Total number of alerts
        by_level: Count per alert level
        recent_alerts: Most recent alerts
        start_time: Summary period start
        end_time: Summary period end
    """
    total_alerts: int = 0
    by_level: dict = field(default_factory=lambda: {
        "INFO": 0,
        "WARNING": 0,
        "HIGH": 0,
        "CRITICAL": 0
    })
    recent_alerts: List[Alert] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_alerts": self.total_alerts,
            "by_level": self.by_level,
            "recent_alerts": [a.to_dict() for a in self.recent_alerts[-10:]],
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None
        }
