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


def _incident_fact_summary(incident: "Incident") -> str:
    """Produce a concise incident summary strictly from persisted fields."""
    risk = str(incident.current_risk_level or "unclassified").lower()
    event_count = len(incident.event_ids or [])
    evidence_count = len(incident.evidence_ids or [])
    camera = str(incident.camera_id or "unknown camera")
    summary = f"{risk.capitalize()} risk incident on {camera}: {event_count} event(s), {evidence_count} evidence record(s)."
    if incident.summary_reason:
        summary = f"{summary} {str(incident.summary_reason).strip()}"
    return summary


# =========================================
# Core Risk Intelligence Models
# =========================================

class Event(Base):
    """Durable, evidence-backed risk events from the video pipeline.

    ``event_id`` is the public, pipeline-generated identifier.  The numeric
    primary key remains for compatibility with the pre-existing ``alerts``
    table, while the evidence columns make an alert independently traceable
    after process restart.
    """
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_evidence_recent", "risk_level", "timestamp"),
    )
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(128), unique=True, index=True)
    alert_id = Column(String(128), index=True)
    # Public incident identifier assigned by the correlation layer.  This is
    # intentionally nullable: incomplete or low-confidence events remain
    # durable evidence without being forced into a fabricated incident.
    incident_id = Column(String(128), index=True)
    event_type = Column(String(50), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    track_id = Column(Integer)
    track_key = Column(String(160), index=True)
    camera_id = Column(String(80), index=True)
    camera_name = Column(String(160))
    object_class = Column(String(100))
    risk_level = Column(String(20))
    risk_score = Column(Float)
    message = Column(Text, nullable=False)
    reason = Column(Text)
    factors = Column(JSONValue)
    zone = Column(String(50))
    zone_id = Column(String(120))
    zone_name = Column(String(160))
    bounding_box = Column(JSONValue)
    snapshot_path = Column(String(512))
    snapshot_status = Column(String(20), nullable=False, default="unavailable")
    clip_path = Column(String(512))
    # ``metadata`` is reserved by SQLAlchemy's declarative base.  Retain the
    # physical column name for compatibility while using a safe Python name.
    event_metadata = Column("metadata", JSONValue)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    
    alerts = relationship("Alert", back_populates="event")
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event_id": self.event_id,
            "alert_id": self.alert_id,
            "incident_id": self.incident_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "track_id": self.track_id,
            "track_key": self.track_key,
            "camera_id": self.camera_id,
            "camera_name": self.camera_name,
            "object_class": self.object_class,
            "risk_level": self.risk_level,
            "risk_score": self.risk_score,
            "message": self.message,
            "reason": self.reason,
            "factors": self.factors,
            "zone": self.zone,
            "zone_id": self.zone_id,
            "zone_name": self.zone_name,
            "bounding_box": self.bounding_box,
            "snapshot_path": self.snapshot_path,
            "snapshot_status": self.snapshot_status,
            "clip_path": self.clip_path,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class EvidenceEmbedding(Base):
    """Rebuildable semantic projection of a durable event, never a second event."""
    __tablename__ = "evidence_embeddings"
    event_id = Column(String(128), primary_key=True)
    model_key = Column(String(200), primary_key=True)
    document_hash = Column(String(64), nullable=False)
    vector = Column(JSONValue, nullable=False)
    indexed_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)


class Observation(Base):
    """Immutable camera-local evidence captured before incident assessment.

    An observation records what a detector, tracker, or relation extractor
    measured.  It deliberately does not state that the scene is dangerous and
    it is not reused as an event, incident, or alert identifier.
    """

    __tablename__ = "observations"
    __table_args__ = (
        Index("ix_observations_camera_epoch_frame", "camera_id", "source_epoch", "frame_id"),
        Index("ix_observations_track_time", "track_key", "captured_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    observation_id = Column(String(160), nullable=False, unique=True, index=True)
    schema_version = Column(String(16), nullable=False, default="1.0")
    camera_id = Column(String(80), nullable=False, index=True)
    source_epoch = Column(String(64), nullable=False, index=True)
    captured_at = Column(DateTime(timezone=True), nullable=False, index=True)
    frame_id = Column(Integer, nullable=False)
    track_key = Column(String(160), index=True)
    related_track_key = Column(String(160), index=True)
    observation_type = Column(String(64), nullable=False, index=True)
    label = Column(String(100), nullable=False)
    model_confidence = Column(Float)
    bounding_box = Column(JSONValue)
    zone_id = Column(String(120), index=True)
    zone_name = Column(String(160))
    event_id = Column(String(128), index=True)
    # ``metadata`` is reserved by SQLAlchemy's declarative base.
    observation_metadata = Column("metadata", JSONValue, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)

    def to_dict(self) -> dict:
        return {
            "observation_id": self.observation_id,
            "schema_version": self.schema_version,
            "camera_id": self.camera_id,
            "source_epoch": self.source_epoch,
            "captured_at": self.captured_at.isoformat() if self.captured_at else None,
            "frame_id": self.frame_id,
            "track_key": self.track_key,
            "related_track_key": self.related_track_key,
            "observation_type": self.observation_type,
            "label": self.label,
            "model_confidence": self.model_confidence,
            "bounding_box": self.bounding_box,
            "zone_id": self.zone_id,
            "zone_name": self.zone_name,
            "event_id": self.event_id,
            "metadata": dict(self.observation_metadata or {}),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class RiskAssessment(Base):
    """Versioned, explainable risk decision for one incident update.

    ``policy_score`` is a rule output, not a probability. Missing evidence is
    recorded explicitly so an operator can distinguish unavailable signals
    from negative evidence.
    """

    __tablename__ = "risk_assessments"
    __table_args__ = (
        Index("ix_risk_assessments_incident_time", "incident_id", "assessed_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    assessment_id = Column(String(160), nullable=False, unique=True, index=True)
    schema_version = Column(String(16), nullable=False, default="1.0")
    policy_version = Column(String(64), nullable=False)
    incident_id = Column(String(128), nullable=False, index=True)
    event_id = Column(String(128), nullable=False, index=True)
    assessed_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now, index=True)
    risk_level = Column(String(20), nullable=False)
    policy_score = Column(Float)
    confidence_status = Column(String(32), nullable=False, default="not_calibrated")
    factor_results = Column(JSONValue, nullable=False, default=list)
    missing_evidence = Column(JSONValue, nullable=False, default=list)
    rationale = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)

    def to_dict(self) -> dict:
        return {
            "assessment_id": self.assessment_id,
            "schema_version": self.schema_version,
            "policy_version": self.policy_version,
            "incident_id": self.incident_id,
            "event_id": self.event_id,
            "assessed_at": self.assessed_at.isoformat() if self.assessed_at else None,
            "risk_level": self.risk_level,
            "policy_score": self.policy_score,
            "confidence_status": self.confidence_status,
            "factor_results": list(self.factor_results or []),
            "missing_evidence": list(self.missing_evidence or []),
            "rationale": self.rationale,
        }


class Incident(Base):
    """A durable, evidence-backed sequence of correlated risk events.

    This is deliberately a lightweight correlation record, not a new risk
    engine.  Its fields are projections of the already persisted events that
    caused it, so it never introduces a synthetic score, track, or reason.
    """

    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'resolved')", name="ck_incidents_status"),
        Index("ix_incidents_active_recent", "status", "camera_id", "last_seen_time"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    incident_id = Column(String(128), nullable=False, unique=True, index=True)
    camera_id = Column(String(80), nullable=False, index=True)
    primary_track_id = Column(String(160), index=True)
    related_track_ids = Column(JSONValue, nullable=False, default=list)
    zone_id = Column(String(120), index=True)
    zone_name = Column(String(160))
    start_time = Column(DateTime(timezone=True), nullable=False)
    last_seen_time = Column(DateTime(timezone=True), nullable=False, index=True)
    current_risk_level = Column(String(20))
    max_risk_score = Column(Float)
    # ``status`` remains the correlation processing state used by the existing
    # worker (active/resolved).  The operator-controlled lifecycle is separate
    # so we do not reinterpret a previously resolved correlation as a human
    # decision, and so existing deployments keep their database constraint.
    status = Column(String(20), nullable=False, default="active", index=True)
    lifecycle_status = Column(String(20), nullable=False, default="open", index=True)
    lifecycle_updated_by = Column(String(160))
    lifecycle_updated_at = Column(DateTime(timezone=True))
    lifecycle_reason = Column(Text)
    event_ids = Column(JSONValue, nullable=False, default=list)
    alert_ids = Column(JSONValue, nullable=False, default=list)
    evidence_ids = Column(JSONValue, nullable=False, default=list)
    risk_types = Column(JSONValue, nullable=False, default=list)
    summary_reason = Column(Text)
    contributing_factors = Column(JSONValue, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)

    def to_dict(self) -> dict:
        return {
            "incident_id": self.incident_id,
            "camera_id": self.camera_id,
            "primary_track_id": self.primary_track_id,
            "related_track_ids": list(self.related_track_ids or []),
            "zone_id": self.zone_id,
            "zone_name": self.zone_name,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "last_seen_time": self.last_seen_time.isoformat() if self.last_seen_time else None,
            "current_risk_level": self.current_risk_level,
            "max_risk_score": self.max_risk_score,
            "status": self.lifecycle_status or ("resolved" if self.status == "resolved" else "open"),
            "processing_status": self.status,
            "lifecycle_updated_by": self.lifecycle_updated_by,
            "lifecycle_updated_at": self.lifecycle_updated_at.isoformat() if self.lifecycle_updated_at else None,
            "lifecycle_reason": self.lifecycle_reason,
            "event_ids": list(self.event_ids or []),
            "alert_ids": list(self.alert_ids or []),
            "evidence_ids": list(self.evidence_ids or []),
            "risk_types": list(self.risk_types or []),
            "summary": _incident_fact_summary(self),
            "summary_reason": self.summary_reason,
            "contributing_factors": list(self.contributing_factors or []),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
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


class OperationalAlert(Base):
    """Durable operator alert state linked to a persisted evidence event.

    The older ``alerts`` table only stores a numeric event relationship and is
    not used by the live AlertManager. This additive table stores the public
    alert identity, acknowledgement, delivery, and cooldown metadata required
    to survive process restart without changing the evidence event schema.
    """

    __tablename__ = "operational_alerts"
    __table_args__ = (
        Index("ix_operational_alerts_active_recent", "acknowledged", "created_at"),
        Index("ix_operational_alerts_cooldown", "cooldown_key", "cooldown_expires_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(String(128), nullable=False, unique=True, index=True)
    event_id = Column(String(128), nullable=False, index=True)
    event_record_id = Column(Integer, ForeignKey("events.id"), nullable=True, index=True)
    track_id = Column(String(160), nullable=True, index=True)
    level = Column(String(20), nullable=False, index=True)
    risk_score = Column(Float, nullable=True)
    message = Column(Text, nullable=False)
    zone = Column(String(160), nullable=True)
    factors = Column(JSONValue, nullable=False, default=list)
    cooldown_key = Column(String(300), nullable=True, index=True)
    cooldown_expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    acknowledged = Column(Boolean, nullable=False, default=False, index=True)
    acknowledged_at = Column(DateTime(timezone=True))
    acknowledged_by = Column(String(100))
    delivery_status = Column(String(32), nullable=False, default="created", index=True)
    delivery_attempts = Column(Integer, nullable=False, default=0)
    delivered_at = Column(DateTime(timezone=True))
    last_delivery_error = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now)

    # Keep the alert API projection connected to the authoritative evidence
    # record.  The public alert ID, the persisted event ID, and the correlated
    # incident must travel together so callers never have to infer links from
    # process-local state.
    event_record = relationship("Event", foreign_keys=[event_record_id])

    def to_dict(self) -> dict:
        evidence = self.event_record
        return {
            "id": self.id,
            "alert_id": self.alert_id,
            "event_id": self.event_id,
            "camera_id": evidence.camera_id if evidence else None,
            "camera_name": evidence.camera_name if evidence else None,
            "incident_id": evidence.incident_id if evidence else None,
            "evidence_id": evidence.event_id if evidence else None,
            "evidence_status": (
                "saved" if evidence and evidence.snapshot_status == "saved" else "unavailable"
            ),
            "snapshot_status": evidence.snapshot_status if evidence else "unavailable",
            "snapshot_path": evidence.snapshot_path if evidence else None,
            "bounding_box": evidence.bounding_box if evidence else None,
            "track_id": self.track_id,
            "risk_level": self.level,
            "risk_score": self.risk_score,
            "message": self.message,
            "zone": self.zone or "",
            "factors": list(self.factors or []),
            "timestamp": self.created_at.isoformat() if self.created_at else None,
            "acknowledged": bool(self.acknowledged),
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "acknowledged_by": self.acknowledged_by,
            "delivery_status": self.delivery_status,
            "delivery_attempts": self.delivery_attempts,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "last_delivery_error": self.last_delivery_error,
            "cooldown_key": self.cooldown_key,
            "cooldown_expires_at": self.cooldown_expires_at.isoformat() if self.cooldown_expires_at else None,
        }


class AuditLog(Base):
    """Append-only operational audit records without secrets or raw prompts.

    The table intentionally stores resource references and structured,
    non-sensitive details only.  In particular, API keys, camera URLs,
    evidence bytes, and agent messages must never be written here.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_resource_recent", "resource_type", "resource_id", "created_at"),
        Index("ix_audit_logs_action_recent", "action", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    action = Column(String(96), nullable=False, index=True)
    actor_id = Column(String(160), nullable=True, index=True)
    resource_type = Column(String(64), nullable=True, index=True)
    resource_id = Column(String(160), nullable=True, index=True)
    details = Column(JSONValue, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utc_now, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "action": self.action,
            "actor_id": self.actor_id,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "details": dict(self.details or {}),
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
