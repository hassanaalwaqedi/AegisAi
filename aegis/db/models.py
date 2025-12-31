"""
AegisAI - Database Models
SQLAlchemy ORM Models for Events, Alerts, and Tracks

Tables:
- events: Risk events with scores and explanations
- alerts: Generated alerts with acknowledgment status
- track_snapshots: Historical track data for analysis
"""

import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    Column, Integer, String, Float, Boolean,
    DateTime, Text, JSON, ForeignKey, Index
)
from sqlalchemy.orm import relationship

from aegis.db.database import Base


def generate_uuid() -> str:
    """Generate a unique event ID."""
    return str(uuid.uuid4())[:12]


class EventModel(Base):
    """
    Risk event record.
    
    Stores individual risk events from the risk engine
    with full context for audit trails.
    """
    __tablename__ = "events"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(12), unique=True, nullable=False, default=generate_uuid)
    
    # Event data
    track_id = Column(Integer, nullable=False, index=True)
    frame_id = Column(Integer, nullable=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    # Risk assessment
    risk_score = Column(Float, nullable=False)
    risk_level = Column(String(20), nullable=False)  # LOW, MEDIUM, HIGH, CRITICAL
    
    # Context
    class_name = Column(String(50), nullable=True)
    zone_name = Column(String(100), nullable=True)
    
    # Explanation (JSON for flexibility)
    factors = Column(JSON, nullable=True)  # List of factor dicts
    explanation = Column(Text, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Indexes for common queries
    __table_args__ = (
        Index('ix_events_level_timestamp', 'risk_level', 'timestamp'),
    )
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "event_id": self.event_id,
            "track_id": self.track_id,
            "frame_id": self.frame_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "risk_score": self.risk_score,
            "risk_level": self.risk_level,
            "class_name": self.class_name,
            "zone_name": self.zone_name,
            "factors": self.factors,
            "explanation": self.explanation,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class AlertModel(Base):
    """
    Generated alert record.
    
    Alerts are derived from events when risk exceeds
    thresholds and cooldowns allow.
    """
    __tablename__ = "alerts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(String(12), unique=True, nullable=False, default=generate_uuid)
    
    # Related event
    event_id = Column(String(12), ForeignKey("events.event_id"), nullable=True)
    event = relationship("EventModel", backref="alerts")
    
    # Alert data
    track_id = Column(Integer, nullable=False, index=True)
    level = Column(String(20), nullable=False)  # INFO, WARNING, HIGH, CRITICAL
    risk_score = Column(Float, nullable=False)
    message = Column(Text, nullable=False)
    
    # Context
    zone = Column(String(100), nullable=True)
    factors = Column(JSON, nullable=True)  # List of factor names
    
    # Status
    acknowledged = Column(Boolean, nullable=False, default=False)
    acknowledged_at = Column(DateTime, nullable=True)
    acknowledged_by = Column(String(100), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "alert_id": self.alert_id,
            "event_id": self.event_id,
            "track_id": self.track_id,
            "level": self.level,
            "risk_score": self.risk_score,
            "message": self.message,
            "zone": self.zone,
            "factors": self.factors,
            "acknowledged": self.acknowledged,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "acknowledged_by": self.acknowledged_by,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class TrackSnapshotModel(Base):
    """
    Track snapshot for historical analysis.
    
    Stores periodic snapshots of tracks for
    post-incident analysis and reporting.
    """
    __tablename__ = "track_snapshots"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Track identification
    track_id = Column(Integer, nullable=False, index=True)
    frame_id = Column(Integer, nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    # Detection data
    class_name = Column(String(50), nullable=True)
    confidence = Column(Float, nullable=True)
    bbox_x1 = Column(Integer, nullable=True)
    bbox_y1 = Column(Integer, nullable=True)
    bbox_x2 = Column(Integer, nullable=True)
    bbox_y2 = Column(Integer, nullable=True)
    
    # Analysis data
    speed = Column(Float, nullable=True)
    direction = Column(Float, nullable=True)
    risk_score = Column(Float, nullable=True)
    
    # Behaviors (JSON array)
    behaviors = Column(JSON, nullable=True)
    
    # Semantic data
    semantic_label = Column(String(200), nullable=True)
    semantic_confidence = Column(Float, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "track_id": self.track_id,
            "frame_id": self.frame_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "class_name": self.class_name,
            "confidence": self.confidence,
            "bbox": [self.bbox_x1, self.bbox_y1, self.bbox_x2, self.bbox_y2],
            "speed": self.speed,
            "direction": self.direction,
            "risk_score": self.risk_score,
            "behaviors": self.behaviors,
            "semantic_label": self.semantic_label,
            "semantic_confidence": self.semantic_confidence,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
