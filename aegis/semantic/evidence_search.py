"""Real multilingual retrieval of stored evidence, with a rebuildable SQL vector index.

The existing live rule query is preserved. This service searches immutable
persisted event descriptions using normalized learned sentence embeddings.
No camera frame, risk probability or visual relationship is synthesized.
"""
from datetime import datetime, timezone
import hashlib
import logging
import math
from pathlib import Path
import threading
import time
from typing import Literal
from pydantic import BaseModel, Field, model_validator

from aegis.database.connection import get_db_session
from aegis.database.repositories import EventRepository
from aegis.database.evidence_search_repository import EvidenceSearchRepository
from aegis.intelligence.event_access import persisted_event_record
from aegis.semantic.embedding import EvidenceEncoder, MODEL_KEY

logger = logging.getLogger(__name__)


class EvidenceSearchRequest(BaseModel):
    query: str = Field(default="", max_length=500)
    similar_to: str | None = Field(default=None, max_length=128)
    camera_id: str | None = Field(default=None, max_length=80)
    event_type: str | None = Field(default=None, max_length=50)
    risk_level: Literal["LOW", "CANDIDATE_MEDIUM", "MEDIUM", "HIGH", "CRITICAL"] | None = None
    start: datetime | None = None
    end: datetime | None = None
    as_of: datetime | None = None
    min_confidence: float = Field(default=0, ge=0, le=1)
    min_similarity: float = Field(default=0.25, ge=-1, le=1)
    sort: Literal["relevance", "newest", "oldest", "risk", "confidence"] = "relevance"
    page: int = Field(default=1, ge=1, le=10000)
    page_size: int = Field(default=6, ge=1, le=50)

    @model_validator(mode="after")
    def valid_query(self):
        self.query = self.query.strip()
        if not self.similar_to and len(self.query) < 3:
            raise ValueError("Enter at least three characters.")
        if self.similar_to and self.query:
            raise ValueError("Choose text search or similar evidence, not both.")
        for name in ("start", "end", "as_of"):
            value = getattr(self, name)
            if value and value.tzinfo is None:
                setattr(self, name, value.replace(tzinfo=timezone.utc))
        if self.start and self.end and self.start > self.end:
            raise ValueError("Start must precede end.")
        return self


class SearchUnavailable(Exception):
    pass


def evidence_document(event):
    # Only observed/stored facts. IDs and storage paths add no semantic meaning.
    return ". ".join(str(value) for value in (
        event.object_class, event.event_type, event.reason or event.message,
        event.zone_name or event.zone, event.risk_level,
    ) if value)


def public_evidence(event):
    record = persisted_event_record(event)
    result = {key: record.get(key) for key in (
        "event_id", "alert_id", "incident_id", "camera_id", "camera_name", "event_type",
        "timestamp", "object_class", "risk_level", "risk_score", "track_id", "zone", "zone_name", "reason",
    )}
    metadata = event.event_metadata or {}
    confidence = metadata.get("confidence")
    result["detection_confidence"] = float(confidence) if isinstance(confidence, (int, float)) and not isinstance(confidence, bool) and math.isfinite(confidence) and 0 <= confidence <= 1 else None
    result["detectors"] = [str(x) for x in metadata.get("model_source", []) if isinstance(x, str)] if isinstance(metadata.get("model_source"), list) else []
    root = Path("data/output/snapshots").resolve()
    path = Path(event.snapshot_path).resolve() if event.snapshot_path else None
    result["snapshot_available"] = bool(event.snapshot_status == "saved" and path and root in path.parents and path.is_file())
    return result


class EvidenceSearchService:
    def __init__(self, encoder=None, session_factory=get_db_session):
        self.encoder = encoder or EvidenceEncoder()
        self.sessions = session_factory
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self.indexing = False
        self.failed = False

    def sync_batch(self):
        if not self._lock.acquire(blocking=False):
            return 0
        try:
            self.indexing = True
            self.encoder.load()
            with self.sessions() as session:
                repo = EvidenceSearchRepository(session, MODEL_KEY)
                rows = repo.pending()
                # Detach read state before slow inference, so writes never wait on a read transaction.
                documents = [(row.event_id, evidence_document(row)) for row in rows]
            if documents:
                vectors = self.encoder.encode([text for _, text in documents])
                with self.sessions() as session:
                    repo = EvidenceSearchRepository(session, MODEL_KEY)
                    for (event_id, text), vector in zip(documents, vectors):
                        repo.save(event_id, vector, hashlib.sha256(text.encode()).hexdigest())
            self.failed = False
            return len(documents)
        except Exception as exc:
            self.failed = True
            logger.warning("Evidence indexing unavailable: %s", type(exc).__name__)
            return 0
        finally:
            self.indexing = False
            self._lock.release()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        def run():
            while not self._stop.is_set():
                processed = self.sync_batch()
                self._stop.wait(0.1 if processed == 32 else 15)
        self._thread = threading.Thread(target=run, name="evidence-index", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def status(self):
        try:
            with self.sessions() as session:
                stats = EvidenceSearchRepository(session, MODEL_KEY).status()
        except Exception as exc:
            raise SearchUnavailable("Evidence storage is unavailable.") from exc
        state = "offline" if self.failed or not self.encoder.ready else "indexing" if self.indexing or stats["pending_evidence"] else "ready"
        return {**stats, "state": state, "model": MODEL_KEY, "similarity": "cosine", "representation": "stored_event_text"}

    def search(self, request):
        started = time.perf_counter()
        if not self.encoder.ready:
            raise SearchUnavailable("Semantic model is unavailable or still loading.")
        as_of = request.as_of or datetime.now(timezone.utc)
        request = request.model_copy(update={"as_of": as_of})
        try:
            with self.sessions() as session:
                repo = EvidenceSearchRepository(session, MODEL_KEY)
                if request.similar_to:
                    source = repo.embedding(request.similar_to)
                    if not source:
                        raise LookupError("Source evidence is not indexed.")
                    vector = source[1].vector
                else:
                    vector = self.encoder.query(request.query)
                ranked = []
                for event, embedding in repo.candidates(request):
                    if event.event_id == request.similar_to:
                        continue
                    score = sum(a*b for a, b in zip(vector, embedding.vector))
                    if score < request.min_similarity:
                        continue
                    record = public_evidence(event)
                    if request.min_confidence and (record["detection_confidence"] is None or record["detection_confidence"] < request.min_confidence):
                        continue
                    record["similarity"] = round(max(-1, min(1, score)), 4)
                    ranked.append(record)
                risk_order = {"LOW": 0, "CANDIDATE_MEDIUM": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
                def key(row):
                    if request.sort in ("newest", "oldest"):
                        return (row["timestamp"] or "", row["event_id"])
                    if request.sort == "risk":
                        return (risk_order.get(row["risk_level"], -1), row["similarity"], row["event_id"])
                    if request.sort == "confidence":
                        return (row["detection_confidence"] if row["detection_confidence"] is not None else -1, row["similarity"], row["event_id"])
                    return (row["similarity"], row["event_id"])
                ranked.sort(key=key, reverse=request.sort != "oldest")
                total = len(ranked)
                offset = (request.page-1)*request.page_size
                index = repo.status()
                return {"results": ranked[offset:offset+request.page_size], "total": total, "page": request.page, "sort": request.sort,
                    "page_size": request.page_size, "has_next": offset+request.page_size < total,
                    "has_previous": request.page > 1, "as_of": as_of, "pending_evidence": index["pending_evidence"],
                    "execution_ms": round((time.perf_counter()-started)*1000, 2)}
        except (LookupError, SearchUnavailable):
            raise
        except Exception as exc:
            logger.warning("Evidence search failed: %s", type(exc).__name__)
            raise SearchUnavailable("Evidence search is temporarily unavailable.") from exc

    def detail(self, event_id):
        with self.sessions() as session:
            event = EventRepository(session).get_by_event_id(event_id)
            if event is None:
                raise LookupError("Evidence not found.")
            repo = EvidenceSearchRepository(session, MODEL_KEY)
            return {"evidence": public_evidence(event), "related": [public_evidence(row) for row in repo.related(event)]}


evidence_search = EvidenceSearchService()
