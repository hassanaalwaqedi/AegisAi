"""
AegisAI - SQLAlchemy ORM Models

All database models for PostgreSQL persistence.
"""

from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, 
    Text, ForeignKey, JSON, Uuid, CheckConstraint, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
import uuid

from .connection import Base


# The active persistence stack supports PostgreSQL and the repository's local
# SQLite deployment.  Keep PostgreSQL's JSONB optimization while using a
# portable JSON representation for SQLite.  Embeddings are persisted as JSON
# arrays in the portable schema rather than PostgreSQL-only ARRAY values.
JSONValue = JSON().with_variant(JSONB, "postgresql")
UUIDValue = Uuid(as_uuid=True)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


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
    factors = Column(JSONValue)
    zone = Column(String(50))
    # ``metadata`` is reserved by SQLAlchemy's declarative base.  Retain the
    # physical column name for compatibility while using a safe Python name.
    event_metadata = Column("metadata", JSONValue)
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
    behaviors_detected = Column(JSONValue, default=[])


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
    
    id = Column(UUIDValue, primary_key=True, default=uuid.uuid4)
    session_id = Column(String(100), unique=True, nullable=False)
    user_hash = Column(String(64))
    intent = Column(String(30))
    scroll_depth_max = Column(Float, default=0.0)
    rage_clicks = Column(Integer, default=0)
    hesitation_count = Column(Integer, default=0)
    decision_path = Column(JSONValue, default=[])
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
    properties = Column(JSONValue, default={})
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class BehaviorEmbedding(Base):
    """Behavior embeddings for clustering."""
    __tablename__ = "behavior_embeddings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), unique=True, nullable=False)
    embedding = Column(JSONValue, nullable=False)
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
    attributes = Column(JSONValue, default={})
    events = Column(JSONValue, default=[])
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class TelemetryMetric(Base):
    """Observability metrics."""
    __tablename__ = "telemetry_metrics"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, index=True)
    value = Column(Float, nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    labels = Column(JSONValue, default={})
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
    context = Column(JSONValue, default={})
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
    
    id = Column(UUIDValue, primary_key=True, default=uuid.uuid4)
    alert_id = Column(String(100), unique=True, nullable=False)
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=False)
    priority = Column(Integer, nullable=False)
    status = Column(String(30), default="open")
    root_cause = Column(JSONValue)
    related_metrics = Column(JSONValue, default=[])
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
    data = Column(JSONValue)
    sql_generated = Column(Text)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class InsightRecord(Base):
    """Generated business insights."""
    __tablename__ = "insights"
    
    id = Column(UUIDValue, primary_key=True, default=uuid.uuid4)
    insight_id = Column(String(100), unique=True, nullable=False)
    insight_type = Column(String(30), nullable=False)
    priority = Column(Integer, nullable=False)
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=False)
    impact = Column(Text)
    confidence = Column(Float, nullable=False)
    data_points = Column(JSONValue, default=[])
    action_items = Column(JSONValue, default=[])
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


# =========================================
# Official system knowledge
# =========================================

class SystemKnowledge(Base):
    """Versioned, administratively maintained facts used to ground Aegis AI."""

    __tablename__ = "system_knowledge"
    __table_args__ = (
        CheckConstraint("visibility IN ('public', 'private')", name="ck_system_knowledge_visibility"),
        CheckConstraint(
            "category IN ('creator_profile', 'creator_contributions', 'project_profile', "
            "'project_purpose', 'project_architecture', 'project_capabilities', "
            "'project_technology', 'project_security', 'project_limitations')",
            name="ck_system_knowledge_category",
        ),
        CheckConstraint("priority >= 0 AND priority <= 1000", name="ck_system_knowledge_priority"),
        CheckConstraint("version >= 1", name="ck_system_knowledge_version"),
        UniqueConstraint("key", "version", name="uq_system_knowledge_key_version"),
        Index("ix_system_knowledge_retrieval", "category", "visibility", "is_active"),
    )

    id = Column(UUIDValue, primary_key=True, default=uuid.uuid4)
    key = Column(String(160), nullable=False, index=True)
    category = Column(String(64), nullable=False, index=True)
    title = Column(String(300), nullable=False)
    content = Column(Text, nullable=False)
    content_ar = Column(Text)
    content_en = Column(Text)
    content_tr = Column(Text)
    structured_data = Column(JSONValue, nullable=False, default=dict)
    visibility = Column(String(16), nullable=False, default="public", index=True)
    priority = Column(Integer, nullable=False, default=100)
    source = Column(String(300), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    version = Column(Integer, nullable=False, default=1)
    created_by = Column(String(160))
    updated_by = Column(String(160))
    published_at = Column(DateTime(timezone=True))
    deleted_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)


class SystemKnowledgeAudit(Base):
    """Append-only audit entries for administrative knowledge changes."""

    __tablename__ = "system_knowledge_audit"
    __table_args__ = (
        Index("ix_system_knowledge_audit_record_created", "record_id", "created_at"),
    )

    id = Column(UUIDValue, primary_key=True, default=uuid.uuid4)
    record_id = Column(UUIDValue, ForeignKey("system_knowledge.id"), nullable=False, index=True)
    key = Column(String(160), nullable=False, index=True)
    action = Column(String(32), nullable=False)
    actor = Column(String(160), nullable=False)
    before = Column(JSONValue)
    after = Column(JSONValue)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)

    record = relationship("SystemKnowledge")
