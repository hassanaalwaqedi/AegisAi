"""
AegisAI - Database Repository Layer

Repository pattern for database operations.
"""

from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError

from .models import (
    Event, Alert, TrackStats, BehavioralSession, BehaviorEvent,
    BehaviorEmbedding, TelemetrySpan, TelemetryMetric, Anomaly,
    SmartAlertRecord, NLQQuery, InsightRecord, ConsentRecord,
    SystemKnowledge, SystemKnowledgeAudit, Incident, OperationalAlert, AuditLog,
    Observation, RiskAssessment,
)


class SystemKnowledgeRepository:
    """Repository for the active SQLAlchemy system-knowledge persistence path."""

    def __init__(self, db: Session):
        self.db = db

    def get(self, record_id):
        return self.db.get(SystemKnowledge, record_id)

    def get_current_by_key(self, key: str):
        return self.db.query(SystemKnowledge).filter(
            SystemKnowledge.key == key,
            SystemKnowledge.is_active.is_(True),
            SystemKnowledge.deleted_at.is_(None),
        ).order_by(desc(SystemKnowledge.version)).first()

    def get_versions(self, key: str):
        return self.db.query(SystemKnowledge).filter(
            SystemKnowledge.key == key,
        ).order_by(desc(SystemKnowledge.version)).all()

    def list_active_public(self):
        return self.db.query(SystemKnowledge).filter(
            SystemKnowledge.is_active.is_(True),
            SystemKnowledge.visibility == "public",
            SystemKnowledge.deleted_at.is_(None),
        ).all()

    def list(self, *, category=None, visibility=None, active_only=False, limit=100, offset=0):
        query = self.db.query(SystemKnowledge)
        if category:
            query = query.filter(SystemKnowledge.category == category)
        if visibility:
            query = query.filter(SystemKnowledge.visibility == visibility)
        if active_only:
            query = query.filter(SystemKnowledge.is_active.is_(True), SystemKnowledge.deleted_at.is_(None))
        return query.order_by(SystemKnowledge.key.asc(), desc(SystemKnowledge.version)).offset(offset).limit(limit).all()

    def add(self, record: SystemKnowledge) -> SystemKnowledge:
        self.db.add(record)
        self.db.flush()
        return record

    def add_audit(self, audit: SystemKnowledgeAudit) -> SystemKnowledgeAudit:
        self.db.add(audit)
        self.db.flush()
        return audit

    def audit_history(self, record_id):
        return self.db.query(SystemKnowledgeAudit).filter(
            SystemKnowledgeAudit.record_id == record_id,
        ).order_by(desc(SystemKnowledgeAudit.created_at)).all()


class EventRepository:
    """Repository for the active SQLAlchemy durable-event path."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create(self, event_type: str, message: str, **kwargs) -> Event:
        event_id = kwargs.get("event_id")
        if event_id:
            evidence_kwargs = dict(kwargs)
            evidence_kwargs.pop("event_id", None)
            event, _ = self.create_or_get_evidence(
                event_id=str(event_id),
                event_type=event_type,
                message=message,
                **evidence_kwargs,
            )
            return event
        event = Event(
            event_type=event_type,
            timestamp=kwargs.get("timestamp", datetime.utcnow()),
            message=message,
            track_id=kwargs.get("track_id"),
            risk_level=kwargs.get("risk_level"),
            risk_score=kwargs.get("risk_score"),
            factors=kwargs.get("factors"),
            zone=kwargs.get("zone"),
            event_metadata=kwargs.get("metadata"),
        )
        self.db.add(event)
        self.db.flush()
        return event

    def create_or_get_evidence(self, *, event_id: str, event_type: str, message: str, **kwargs) -> tuple[Event, bool]:
        """Create one durable evidence record per public event identifier.

        The alert manager already controls alert cooldowns.  This extra
        database-level identity guard protects against repeated delivery or a
        retry racing with the first write without changing that alert logic.
        """
        normalized_event_id = str(event_id).strip()
        if not normalized_event_id:
            raise ValueError("A durable evidence record requires an event_id")

        existing = self.get_by_event_id(normalized_event_id)
        if existing is not None:
            return existing, False

        event = Event(
            event_id=normalized_event_id,
            alert_id=kwargs.get("alert_id"),
            incident_id=kwargs.get("incident_id"),
            event_type=event_type,
            timestamp=kwargs.get("timestamp", datetime.utcnow()),
            message=message,
            reason=kwargs.get("reason") or message,
            track_id=kwargs.get("track_id"),
            track_key=kwargs.get("track_key"),
            camera_id=kwargs.get("camera_id"),
            camera_name=kwargs.get("camera_name"),
            object_class=kwargs.get("object_class"),
            risk_level=kwargs.get("risk_level"),
            risk_score=kwargs.get("risk_score"),
            factors=kwargs.get("factors") or [],
            zone=kwargs.get("zone"),
            zone_id=kwargs.get("zone_id"),
            zone_name=kwargs.get("zone_name"),
            bounding_box=kwargs.get("bounding_box"),
            snapshot_path=kwargs.get("snapshot_path"),
            snapshot_status=kwargs.get("snapshot_status") or "unavailable",
            clip_path=kwargs.get("clip_path"),
            event_metadata=kwargs.get("metadata"),
        )

        try:
            # A savepoint keeps the caller's transaction usable when two
            # workers race to write the same externally assigned event ID.
            with self.db.begin_nested():
                self.db.add(event)
                self.db.flush()
            return event, True
        except IntegrityError:
            existing = self.get_by_event_id(normalized_event_id)
            if existing is not None:
                return existing, False
            raise
    
    def get_recent(self, limit: int = 50) -> List[Event]:
        return self.db.query(Event).order_by(desc(Event.timestamp)).limit(limit).all()
    
    def get_by_risk_level(self, level: str, limit: int = 50) -> List[Event]:
        return self.db.query(Event).filter(Event.risk_level == level)\
            .order_by(desc(Event.timestamp)).limit(limit).all()

    def get_by_event_id(self, event_id: str) -> Optional[Event]:
        return self.db.query(Event).filter(Event.event_id == event_id).one_or_none()

    def get_by_alert_id(self, alert_id: str) -> Optional[Event]:
        return self.db.query(Event).filter(Event.alert_id == alert_id).order_by(desc(Event.timestamp)).first()

    def get_recent_evidence(self, limit: int = 50, risk_level: Optional[str] = None) -> List[Event]:
        query = self.db.query(Event).filter(Event.event_id.isnot(None))
        if risk_level:
            query = query.filter(Event.risk_level == risk_level.upper())
        return query.order_by(desc(Event.timestamp)).limit(limit).all()

    def get_by_incident_id(self, incident_id: str) -> List[Event]:
        return self.db.query(Event).filter(
            Event.incident_id == incident_id,
        ).order_by(Event.timestamp.asc(), Event.id.asc()).all()


class ObservationRepository:
    """Append-only persistence for camera observations.

    Callers provide a deterministic observation ID so replay and retries are
    idempotent.  This repository intentionally has no risk-scoring behavior.
    """

    def __init__(self, db: Session):
        self.db = db

    def create_or_get(self, *, observation_id: str, **kwargs) -> tuple[Observation, bool]:
        normalized_id = str(observation_id).strip()
        if not normalized_id:
            raise ValueError("An observation requires an observation_id")
        existing = self.get_by_observation_id(normalized_id)
        if existing is not None:
            return existing, False

        observation = Observation(
            observation_id=normalized_id,
            schema_version=str(kwargs.get("schema_version") or "1.0"),
            camera_id=str(kwargs["camera_id"]),
            source_epoch=str(kwargs["source_epoch"]),
            captured_at=kwargs["captured_at"],
            frame_id=int(kwargs["frame_id"]),
            track_key=kwargs.get("track_key"),
            related_track_key=kwargs.get("related_track_key"),
            observation_type=str(kwargs["observation_type"]),
            label=str(kwargs["label"]),
            model_confidence=kwargs.get("model_confidence"),
            bounding_box=kwargs.get("bounding_box"),
            zone_id=kwargs.get("zone_id"),
            zone_name=kwargs.get("zone_name"),
            event_id=kwargs.get("event_id"),
            observation_metadata=dict(kwargs.get("metadata") or {}),
        )
        try:
            with self.db.begin_nested():
                self.db.add(observation)
                self.db.flush()
            return observation, True
        except IntegrityError:
            existing = self.get_by_observation_id(normalized_id)
            if existing is not None:
                return existing, False
            raise

    def get_by_observation_id(self, observation_id: str) -> Optional[Observation]:
        return self.db.query(Observation).filter(
            Observation.observation_id == observation_id,
        ).one_or_none()

    def list_for_event(self, event_id: str) -> List[Observation]:
        return self.db.query(Observation).filter(
            Observation.event_id == event_id,
        ).order_by(Observation.captured_at.asc(), Observation.id.asc()).all()

    def list_for_track(self, track_key: str, *, limit: int = 200) -> List[Observation]:
        return self.db.query(Observation).filter(
            Observation.track_key == track_key,
        ).order_by(desc(Observation.captured_at), desc(Observation.id)).limit(limit).all()

    def attach_to_event(self, observation_ids: List[str], event_id: str) -> int:
        """Link already-committed observations to their derived event.

        Observations remain valid evidence if event creation fails; this link
        is intentionally additive rather than a prerequisite for capture.
        """
        identifiers = [str(value).strip() for value in observation_ids if str(value).strip()]
        if not identifiers or not event_id:
            return 0
        return self.db.query(Observation).filter(
            Observation.observation_id.in_(identifiers),
        ).update(
            {Observation.event_id: str(event_id)},
            synchronize_session=False,
        )


class RiskAssessmentRepository:
    """Persistence boundary for versioned incident risk assessments."""

    def __init__(self, db: Session):
        self.db = db

    def create_or_get(self, *, assessment_id: str, **kwargs) -> tuple[RiskAssessment, bool]:
        existing = self.db.query(RiskAssessment).filter(
            RiskAssessment.assessment_id == str(assessment_id),
        ).one_or_none()
        if existing is not None:
            return existing, False
        record = RiskAssessment(
            assessment_id=str(assessment_id),
            schema_version=str(kwargs.get("schema_version") or "1.0"),
            policy_version=str(kwargs["policy_version"]),
            incident_id=str(kwargs["incident_id"]),
            event_id=str(kwargs["event_id"]),
            assessed_at=kwargs["assessed_at"],
            risk_level=str(kwargs["risk_level"]),
            policy_score=kwargs.get("policy_score"),
            confidence_status=str(kwargs.get("confidence_status") or "not_calibrated"),
            factor_results=list(kwargs.get("factor_results") or []),
            missing_evidence=list(kwargs.get("missing_evidence") or []),
            rationale=str(kwargs["rationale"]),
        )
        self.db.add(record)
        self.db.flush()
        return record, True

    def list_for_incident(self, incident_id: str) -> List[RiskAssessment]:
        return self.db.query(RiskAssessment).filter(
            RiskAssessment.incident_id == incident_id,
        ).order_by(RiskAssessment.assessed_at.asc(), RiskAssessment.id.asc()).all()


class IncidentRepository:
    """Database access for the one active incident-correlation path."""

    def __init__(self, db: Session):
        self.db = db

    def add(self, incident: Incident) -> Incident:
        self.db.add(incident)
        self.db.flush()
        return incident

    def get_by_incident_id(self, incident_id: str) -> Optional[Incident]:
        return self.db.query(Incident).filter(
            Incident.incident_id == incident_id,
        ).one_or_none()

    def get_active_candidates(self, *, camera_id: str, since: datetime, limit: int = 50) -> List[Incident]:
        return self.db.query(Incident).filter(
            Incident.status == "active",
            Incident.camera_id == camera_id,
            Incident.last_seen_time >= since,
        ).order_by(desc(Incident.last_seen_time)).limit(limit).all()

    def list_active(self, limit: int = 50) -> List[Incident]:
        return self.db.query(Incident).filter(
            Incident.status == "active",
        ).order_by(desc(Incident.last_seen_time)).limit(limit).all()

    def list_recent(self, limit: int = 50) -> List[Incident]:
        return self.db.query(Incident).order_by(desc(Incident.last_seen_time)).limit(limit).all()

    def active_count(self) -> int:
        return self.db.query(Incident).filter(Incident.status == "active").count()

    def set_lifecycle_status(
        self,
        incident_id: str,
        lifecycle_status: str,
        *,
        actor_id: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Optional[Incident]:
        """Record an operator decision while retaining correlation state.

        Terminal lifecycle values also close correlation so late frames cannot
        silently re-open a human-resolved or false-positive incident.
        """
        normalized = str(lifecycle_status or "").strip().lower()
        allowed = {"open", "acknowledged", "under_review", "resolved", "false_positive"}
        if normalized not in allowed:
            raise ValueError("Unsupported incident lifecycle status.")
        incident = self.get_by_incident_id(incident_id)
        if incident is None:
            return None
        incident.lifecycle_status = normalized
        incident.lifecycle_updated_by = actor_id or "api-key-operator"
        incident.lifecycle_updated_at = datetime.now(timezone.utc)
        incident.lifecycle_reason = str(reason).strip() if reason and str(reason).strip() else None
        if normalized in {"resolved", "false_positive"}:
            incident.status = "resolved"
        else:
            incident.status = "active"
        self.db.flush()
        return incident

    def resolve_expired(self, *, cutoff: datetime, resolved_at: Optional[datetime] = None) -> int:
        now = resolved_at or datetime.now(timezone.utc)
        return self.db.query(Incident).filter(
            Incident.status == "active",
            Incident.lifecycle_status.in_(("open", "acknowledged")),
            Incident.last_seen_time < cutoff,
        ).update(
            {
                Incident.status: "resolved",
                Incident.lifecycle_status: "resolved",
                Incident.lifecycle_updated_at: now,
                Incident.updated_at: now,
            },
            synchronize_session="fetch",
        )


class AuditLogRepository:
    """Database access for append-only security and operator audit records."""

    def __init__(self, db: Session):
        self.db = db

    def append(
        self,
        *,
        action: str,
        actor_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> AuditLog:
        record = AuditLog(
            action=str(action).strip(),
            actor_id=str(actor_id).strip() if actor_id else None,
            resource_type=str(resource_type).strip() if resource_type else None,
            resource_id=str(resource_id).strip() if resource_id else None,
            details=dict(details or {}),
        )
        self.db.add(record)
        self.db.flush()
        return record

    def list_recent(self, limit: int = 100) -> List[AuditLog]:
        return self.db.query(AuditLog).order_by(desc(AuditLog.created_at), desc(AuditLog.id)).limit(limit).all()


class OperationalAlertRepository:
    """Repository for durable operator alert lifecycle state."""

    def __init__(self, db: Session):
        self.db = db

    def create_or_get(
        self,
        *,
        alert_id: str,
        event_id: str,
        event_record_id: Optional[int],
        track_id: Optional[str],
        level: str,
        risk_score: Optional[float],
        message: str,
        zone: Optional[str],
        factors: Optional[list],
        cooldown_key: Optional[str],
        cooldown_expires_at: Optional[datetime],
        delivery_status: str,
        delivery_attempts: int,
        delivered_at: Optional[datetime],
        last_delivery_error: Optional[str],
    ) -> OperationalAlert:
        existing = self.get_by_alert_id(alert_id)
        if existing is not None:
            return existing
        record = OperationalAlert(
            alert_id=alert_id,
            event_id=event_id,
            event_record_id=event_record_id,
            track_id=track_id,
            level=level,
            risk_score=risk_score,
            message=message,
            zone=zone,
            factors=list(factors or []),
            cooldown_key=cooldown_key,
            cooldown_expires_at=cooldown_expires_at,
            delivery_status=delivery_status,
            delivery_attempts=max(0, int(delivery_attempts or 0)),
            delivered_at=delivered_at,
            last_delivery_error=last_delivery_error,
        )
        self.db.add(record)
        self.db.flush()
        return record

    def get_by_alert_id(self, alert_id: str) -> Optional[OperationalAlert]:
        return self.db.query(OperationalAlert).filter(
            OperationalAlert.alert_id == alert_id,
        ).one_or_none()

    def get_by_event_id(self, event_id: str) -> Optional[OperationalAlert]:
        return self.db.query(OperationalAlert).filter(
            OperationalAlert.event_id == event_id,
        ).order_by(desc(OperationalAlert.created_at)).first()

    def get_recent(self, limit: int = 50, level: Optional[str] = None) -> List[OperationalAlert]:
        query = self.db.query(OperationalAlert)
        if level:
            query = query.filter(OperationalAlert.level == level.upper())
        return query.order_by(desc(OperationalAlert.created_at)).limit(limit).all()

    def get_active(self, limit: int = 50) -> List[OperationalAlert]:
        return self.db.query(OperationalAlert).filter(
            OperationalAlert.acknowledged.is_(False),
        ).order_by(desc(OperationalAlert.created_at)).limit(limit).all()

    def acknowledge(self, alert_id: str, acknowledged_by: str = "api-key-operator") -> Optional[OperationalAlert]:
        record = self.get_by_alert_id(alert_id) or self.get_by_event_id(alert_id)
        if record is None:
            return None
        if not record.acknowledged:
            record.acknowledged = True
            record.acknowledged_at = datetime.now(timezone.utc)
            record.acknowledged_by = acknowledged_by
            self.db.flush()
        return record

    def active_cooldown(self, cooldown_key: str, now: Optional[datetime] = None) -> Optional[OperationalAlert]:
        if not cooldown_key:
            return None
        observed_at = now or datetime.now(timezone.utc)
        return self.db.query(OperationalAlert).filter(
            OperationalAlert.cooldown_key == cooldown_key,
            OperationalAlert.cooldown_expires_at.isnot(None),
            OperationalAlert.cooldown_expires_at > observed_at,
        ).order_by(desc(OperationalAlert.created_at)).first()

    def summary(self) -> dict:
        records = self.db.query(OperationalAlert).all()
        by_level = {"INFO": 0, "WARNING": 0, "HIGH": 0, "CRITICAL": 0}
        for record in records:
            if record.level in by_level:
                by_level[record.level] += 1
        return {
            "total_alerts": len(records),
            "by_level": by_level,
            "active": sum(1 for record in records if not record.acknowledged),
        }


class BehavioralSessionRepository:
    """Repository for behavioral sessions."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_or_create(self, session_id: str) -> BehavioralSession:
        session = self.db.query(BehavioralSession)\
            .filter(BehavioralSession.session_id == session_id).first()
        if not session:
            session = BehavioralSession(session_id=session_id)
            self.db.add(session)
            self.db.flush()
        return session
    
    def update(self, session_id: str, **kwargs) -> Optional[BehavioralSession]:
        session = self.get_or_create(session_id)
        for key, value in kwargs.items():
            if hasattr(session, key):
                setattr(session, key, value)
        session.updated_at = datetime.utcnow()
        return session
    
    def add_event(self, session_id: str, event_type: str, properties: dict = None):
        event = BehaviorEvent(
            session_id=session_id,
            event_type=event_type,
            timestamp=datetime.utcnow(),
            properties=properties or {},
        )
        self.db.add(event)
        
        # Update session event count
        session = self.get_or_create(session_id)
        session.event_count = (session.event_count or 0) + 1
        
        return event


class TelemetryRepository:
    """Repository for telemetry data."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def save_span(self, span_data: dict) -> TelemetrySpan:
        span = TelemetrySpan(**span_data)
        self.db.add(span)
        return span
    
    def save_metric(self, name: str, value: float, labels: dict = None, unit: str = ""):
        metric = TelemetryMetric(
            name=name,
            value=value,
            timestamp=datetime.utcnow(),
            labels=labels or {},
            unit=unit,
        )
        self.db.add(metric)
        return metric
    
    def get_metrics(self, name: str, limit: int = 100) -> List[TelemetryMetric]:
        return self.db.query(TelemetryMetric)\
            .filter(TelemetryMetric.name == name)\
            .order_by(desc(TelemetryMetric.timestamp))\
            .limit(limit).all()


class AnomalyRepository:
    """Repository for anomalies."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def save(self, anomaly_type: str, severity: str, metric_name: str, 
             current_value: float, expected_value: float, deviation: float,
             context: dict = None) -> Anomaly:
        anomaly = Anomaly(
            anomaly_type=anomaly_type,
            severity=severity,
            metric_name=metric_name,
            current_value=current_value,
            expected_value=expected_value,
            deviation=deviation,
            context=context or {},
        )
        self.db.add(anomaly)
        return anomaly
    
    def get_recent(self, limit: int = 50) -> List[Anomaly]:
        return self.db.query(Anomaly).order_by(desc(Anomaly.created_at)).limit(limit).all()


class AlertRepository:
    """Repository for smart alerts."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create(self, alert_id: str, title: str, description: str, 
               priority: int, root_cause: dict = None) -> SmartAlertRecord:
        alert = SmartAlertRecord(
            alert_id=alert_id,
            title=title,
            description=description,
            priority=priority,
            root_cause=root_cause,
        )
        self.db.add(alert)
        return alert
    
    def get_open(self) -> List[SmartAlertRecord]:
        return self.db.query(SmartAlertRecord)\
            .filter(SmartAlertRecord.status.in_(["open", "acknowledged"]))\
            .order_by(desc(SmartAlertRecord.created_at)).all()
    
    def resolve(self, alert_id: str) -> bool:
        alert = self.db.query(SmartAlertRecord)\
            .filter(SmartAlertRecord.alert_id == alert_id).first()
        if alert:
            alert.status = "resolved"
            alert.resolved_at = datetime.utcnow()
            return True
        return False


class NLQRepository:
    """Repository for NLQ queries."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def save_query(self, query: str, query_type: str, answer: str, 
                   confidence: float, data: dict = None) -> NLQQuery:
        nlq = NLQQuery(
            query=query,
            query_type=query_type,
            answer=answer,
            confidence=confidence,
            data=data,
        )
        self.db.add(nlq)
        return nlq
    
    def get_history(self, limit: int = 20) -> List[NLQQuery]:
        return self.db.query(NLQQuery).order_by(desc(NLQQuery.created_at)).limit(limit).all()


class InsightRepository:
    """Repository for insights."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def save(self, insight_id: str, insight_type: str, priority: int,
             title: str, description: str, confidence: float, **kwargs) -> InsightRecord:
        insight = InsightRecord(
            insight_id=insight_id,
            insight_type=insight_type,
            priority=priority,
            title=title,
            description=description,
            confidence=confidence,
            impact=kwargs.get("impact"),
            data_points=kwargs.get("data_points", []),
            action_items=kwargs.get("action_items", []),
        )
        self.db.add(insight)
        return insight
    
    def get_recent(self, limit: int = 20) -> List[InsightRecord]:
        return self.db.query(InsightRecord).order_by(desc(InsightRecord.created_at)).limit(limit).all()


class ConsentRepository:
    """Repository for consent records."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def save(self, user_hash: str, consent_type: str, granted: bool,
             ip_address: str = None, user_agent: str = None) -> ConsentRecord:
        record = ConsentRecord(
            user_hash=user_hash,
            consent_type=consent_type,
            granted=granted,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(record)
        return record
    
    def get_latest(self, user_hash: str) -> List[ConsentRecord]:
        return self.db.query(ConsentRecord)\
            .filter(ConsentRecord.user_hash == user_hash)\
            .order_by(desc(ConsentRecord.created_at)).all()
