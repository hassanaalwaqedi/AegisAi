"""Database access for the derived evidence index; events remain authoritative."""
from datetime import datetime, timezone, timedelta
from sqlalchemy import and_, func, or_
from aegis.database.models import Event, EvidenceEmbedding


class EvidenceSearchRepository:
    def __init__(self, session, model_key):
        self.session = session
        self.model_key = model_key

    def indexed(self):
        return self.session.query(Event, EvidenceEmbedding).join(EvidenceEmbedding, and_(
            Event.event_id == EvidenceEmbedding.event_id,
            EvidenceEmbedding.model_key == self.model_key,
        ))

    def pending(self, limit=32):
        return self.session.query(Event).outerjoin(EvidenceEmbedding, and_(
            Event.event_id == EvidenceEmbedding.event_id,
            EvidenceEmbedding.model_key == self.model_key,
        )).filter(Event.event_id.isnot(None), EvidenceEmbedding.event_id.is_(None)).order_by(Event.id).limit(limit).all()

    def save(self, event_id, vector, document_hash):
        self.session.merge(EvidenceEmbedding(event_id=event_id, model_key=self.model_key,
            vector=vector, document_hash=document_hash, indexed_at=datetime.now(timezone.utc)))

    def status(self):
        total = self.session.query(func.count(Event.id)).filter(Event.event_id.isnot(None)).scalar()
        indexed = self.indexed().count()
        last_sync = self.indexed().with_entities(func.max(EvidenceEmbedding.indexed_at)).scalar()
        types = [row[0] for row in self.session.query(Event.event_type).filter(Event.event_id.isnot(None)).distinct().order_by(Event.event_type)]
        return {"total_evidence": total, "indexed_evidence": indexed, "pending_evidence": max(0, total-indexed),
                "last_sync": last_sync, "event_types": types}

    def candidates(self, request):
        query = self.indexed()
        for column, value in [(Event.camera_id, request.camera_id), (Event.risk_level, request.risk_level), (Event.event_type, request.event_type)]:
            if value:
                query = query.filter(column == value)
        if request.start:
            query = query.filter(Event.timestamp >= request.start)
        if request.end:
            query = query.filter(Event.timestamp <= request.end)
        if request.as_of:
            query = query.filter(Event.created_at <= request.as_of)
        return query.order_by(Event.id).yield_per(256)

    def embedding(self, event_id):
        return self.indexed().filter(Event.event_id == event_id).first()

    def related(self, event, limit=8):
        relations = []
        if event.incident_id:
            relations.append(Event.incident_id == event.incident_id)
        if event.track_key:
            relations.append(Event.track_key == event.track_key)
        if event.camera_id and event.timestamp:
            relations.append(and_(Event.camera_id == event.camera_id,
                Event.timestamp >= event.timestamp - timedelta(minutes=5),
                Event.timestamp <= event.timestamp + timedelta(minutes=5)))
        if not relations:
            return []
        return self.session.query(Event).filter(Event.event_id.isnot(None), Event.event_id != event.event_id,
            or_(*relations)).order_by(Event.timestamp.desc(), Event.event_id).limit(limit).all()
