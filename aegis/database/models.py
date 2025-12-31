"""
AegisAI - SQLAlchemy ORM Models

All database models for PostgreSQL persistence.
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, 
    Text, ForeignKey, ARRAY, JSON
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid

from .connection import Base


# =========================================
# Core Risk Intelligence Models
# =========================================

class Event(Base):
    """Risk events from video processing pipeline."""
    __tablename__ = "events"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(50), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    track_id = Column(Integer)
    risk_level = Column(String(20))
    risk_score = Column(Float)
    message = Column(Text, nullable=False)
    factors = Column(JSONB)
    zone = Column(String(50))
    metadata = Column(JSONB)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    
    alerts = relationship("Alert", back_populates="event")
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "track_id": self.track_id,
            "risk_level": self.risk_level,
            "risk_score": self.risk_score,
            "message": self.message,
            "factors": self.factors,
            "zone": self.zone,
        }


class Alert(Base):
    """Alerts generated from events."""
    __tablename__ = "alerts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    level = Column(String(20), nullable=False)
    acknowledged = Column(Boolean, default=False)
    acknowledged_at = Column(DateTime(timezone=True))
    acknowledged_by = Column(String(100))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    
    event = relationship("Event", back_populates="alerts")
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event_id": self.event_id,
            "level": self.level,
            "acknowledged": self.acknowledged,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class TrackStats(Base):
    """Statistics for tracked objects."""
    __tablename__ = "track_stats"
    
    track_id = Column(Integer, primary_key=True)
    class_name = Column(String(50), nullable=False)
    first_seen = Column(DateTime(timezone=True), nullable=False)
    last_seen = Column(DateTime(timezone=True), nullable=False)
    total_frames = Column(Integer, default=0)
    max_risk_score = Column(Float, default=0.0)
    behaviors_detected = Column(JSONB, default=[])


class SessionRecord(Base):
    """Processing session records."""
    __tablename__ = "sessions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True))
    total_frames = Column(Integer, default=0)
    total_detections = Column(Integer, default=0)
    total_tracks = Column(Integer, default=0)
    total_alerts = Column(Integer, default=0)
    avg_fps = Column(Float, default=0.0)


# =========================================
# Analytics Models
# =========================================

class BehavioralSession(Base):
    """User behavioral sessions for analytics."""
    __tablename__ = "behavioral_sessions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(String(100), unique=True, nullable=False)
    user_hash = Column(String(64))
    intent = Column(String(30))
    scroll_depth_max = Column(Float, default=0.0)
    rage_clicks = Column(Integer, default=0)
    hesitation_count = Column(Integer, default=0)
    decision_path = Column(JSONB, default=[])
    event_count = Column(Integer, default=0)
    churn_probability = Column(Float)
    conversion_probability = Column(Float)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "intent": self.intent,
            "scroll_depth_max": self.scroll_depth_max,
            "rage_clicks": self.rage_clicks,
            "hesitation_count": self.hesitation_count,
            "event_count": self.event_count,
            "churn_probability": self.churn_probability,
            "conversion_probability": self.conversion_probability,
        }


class BehaviorEvent(Base):
    """Individual behavioral events."""
    __tablename__ = "behavior_events"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), nullable=False, index=True)
    event_type = Column(String(50), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    properties = Column(JSONB, default={})
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class BehaviorEmbedding(Base):
    """Behavior embeddings for clustering."""
    __tablename__ = "behavior_embeddings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), unique=True, nullable=False)
    embedding = Column(ARRAY(Float), nullable=False)
    cluster_id = Column(Integer)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


# =========================================
# Observability Models
# =========================================

class TelemetrySpan(Base):
    """Distributed tracing spans."""
    __tablename__ = "telemetry_spans"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    trace_id = Column(String(100), nullable=False, index=True)
    span_id = Column(String(100), nullable=False)
    parent_id = Column(String(100))
    name = Column(String(200), nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True))
    duration_ms = Column(Float)
    status = Column(String(20), default="ok")
    attributes = Column(JSONB, default={})
    events = Column(JSONB, default=[])
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class TelemetryMetric(Base):
    """Observability metrics."""
    __tablename__ = "telemetry_metrics"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, index=True)
    value = Column(Float, nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    labels = Column(JSONB, default={})
    unit = Column(String(30))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class Anomaly(Base):
    """Detected anomalies."""
    __tablename__ = "anomalies"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    anomaly_type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False)
    metric_name = Column(String(200), nullable=False)
    current_value = Column(Float, nullable=False)
    expected_value = Column(Float, nullable=False)
    deviation = Column(Float, nullable=False)
    context = Column(JSONB, default={})
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "anomaly_type": self.anomaly_type,
            "severity": self.severity,
            "metric_name": self.metric_name,
            "current_value": self.current_value,
            "expected_value": self.expected_value,
            "deviation": self.deviation,
            "context": self.context,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SmartAlertRecord(Base):
    """Smart alerts with root cause analysis."""
    __tablename__ = "smart_alerts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alert_id = Column(String(100), unique=True, nullable=False)
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=False)
    priority = Column(Integer, nullable=False)
    status = Column(String(30), default="open")
    root_cause = Column(JSONB)
    related_metrics = Column(JSONB, default=[])
    auto_heal_attempted = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    resolved_at = Column(DateTime(timezone=True))
    
    def to_dict(self) -> dict:
        return {
            "alert_id": self.alert_id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "status": self.status,
            "root_cause": self.root_cause,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


# =========================================
# NLQ / Intelligence Models
# =========================================

class NLQQuery(Base):
    """Natural language queries."""
    __tablename__ = "nlq_queries"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    query = Column(Text, nullable=False)
    query_type = Column(String(30), nullable=False)
    answer = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False)
    data = Column(JSONB)
    sql_generated = Column(Text)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class InsightRecord(Base):
    """Generated business insights."""
    __tablename__ = "insights"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    insight_id = Column(String(100), unique=True, nullable=False)
    insight_type = Column(String(30), nullable=False)
    priority = Column(Integer, nullable=False)
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=False)
    impact = Column(Text)
    confidence = Column(Float, nullable=False)
    data_points = Column(JSONB, default=[])
    action_items = Column(JSONB, default=[])
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    
    def to_dict(self) -> dict:
        return {
            "insight_id": self.insight_id,
            "insight_type": self.insight_type,
            "priority": self.priority,
            "title": self.title,
            "description": self.description,
            "impact": self.impact,
            "confidence": self.confidence,
            "data_points": self.data_points,
            "action_items": self.action_items,
        }


# =========================================
# Privacy / Consent Models
# =========================================

class ConsentRecord(Base):
    """User consent records for GDPR/CCPA."""
    __tablename__ = "consent_records"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_hash = Column(String(64), nullable=False, index=True)
    consent_type = Column(String(30), nullable=False)
    granted = Column(Boolean, nullable=False)
    ip_address = Column(String(45))
    user_agent = Column(Text)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
