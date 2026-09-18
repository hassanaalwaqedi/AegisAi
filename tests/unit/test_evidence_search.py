"""Tests for the derived, rebuildable semantic evidence index."""

from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from aegis.database.connection import Base
from aegis.database.repositories import EventRepository
from aegis.semantic.evidence_search import EvidenceSearchRequest, EvidenceSearchService
import aegis.database.models  # noqa: F401 - register mappings


class FakeEncoder:
    """A deterministic encoder for retrieval behavior, without loading a model."""

    ready = False

    def load(self):
        self.ready = True

    def encode(self, texts):
        return [self.query(text) for text in texts]

    def query(self, text):
        lowered = text.lower()
        return [1.0, 0.0] if "person" in lowered or "restricted" in lowered else [0.0, 1.0]


@pytest.fixture()
def evidence_service(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'evidence-search.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    @contextmanager
    def sessions():
        with Session.begin() as session:
            yield session

    timestamp = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
    with Session.begin() as session:
        repo = EventRepository(session)
        repo.create_or_get_evidence(
            event_id="evt-person", event_type="risk_alert", message="Person entered restricted zone.",
            reason="Person entered restricted zone.", timestamp=timestamp, camera_id="north-gate",
            camera_name="North Gate", object_class="person", risk_level="HIGH", risk_score=0.8,
            track_id=17, track_key="north-gate:17", incident_id="inc-1", zone_name="Restricted Gate",
            zone="Restricted Gate", snapshot_status="unavailable", metadata={"confidence": 0.93},
        )
        repo.create_or_get_evidence(
            event_id="evt-vehicle", event_type="observation", message="Vehicle in parking area.",
            reason="Vehicle in parking area.", timestamp=timestamp, camera_id="car-park",
            camera_name="Car Park", object_class="vehicle", risk_level="LOW", risk_score=0.2,
            track_id=4, track_key="car-park:4", snapshot_status="unavailable", metadata={"confidence": 0.55},
        )

    service = EvidenceSearchService(encoder=FakeEncoder(), session_factory=sessions)
    assert service.sync_batch() == 2
    yield service
    engine.dispose()


def test_indexes_persisted_evidence_and_applies_backend_filters(evidence_service):
    status = evidence_service.status()
    assert status["state"] == "ready"
    assert status["total_evidence"] == 2
    assert status["indexed_evidence"] == 2

    result = evidence_service.search(EvidenceSearchRequest(
        query="person", camera_id="north-gate", min_confidence=0.9,
    ))

    assert result["total"] == 1
    assert result["results"][0]["event_id"] == "evt-person"
    assert result["results"][0]["detection_confidence"] == 0.93
    assert result["results"][0]["similarity"] == 1.0


def test_similar_evidence_uses_the_persisted_vector_and_excludes_source(evidence_service):
    result = evidence_service.search(EvidenceSearchRequest(similar_to="evt-person", min_similarity=-1))

    assert result["total"] == 1
    assert result["results"][0]["event_id"] == "evt-vehicle"
    assert result["as_of"].tzinfo is not None
