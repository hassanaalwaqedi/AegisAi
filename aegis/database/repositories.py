"""
AegisAI - Database Repository Layer

Repository pattern for database operations.
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import desc

from .models import (
    Event, Alert, TrackStats, BehavioralSession, BehaviorEvent,
    BehaviorEmbedding, TelemetrySpan, TelemetryMetric, Anomaly,
    SmartAlertRecord, NLQQuery, InsightRecord, ConsentRecord
)


class EventRepository:
    """Repository for Event operations."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create(self, event_type: str, message: str, **kwargs) -> Event:
        event = Event(
            event_type=event_type,
            timestamp=kwargs.get("timestamp", datetime.utcnow()),
            message=message,
            track_id=kwargs.get("track_id"),
            risk_level=kwargs.get("risk_level"),
            risk_score=kwargs.get("risk_score"),
            factors=kwargs.get("factors"),
            zone=kwargs.get("zone"),
            metadata=kwargs.get("metadata"),
        )
        self.db.add(event)
        self.db.flush()
        return event
    
    def get_recent(self, limit: int = 50) -> List[Event]:
        return self.db.query(Event).order_by(desc(Event.timestamp)).limit(limit).all()
    
    def get_by_risk_level(self, level: str, limit: int = 50) -> List[Event]:
        return self.db.query(Event).filter(Event.risk_level == level)\
            .order_by(desc(Event.timestamp)).limit(limit).all()


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
