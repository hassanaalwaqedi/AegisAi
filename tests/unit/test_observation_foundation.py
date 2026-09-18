"""Regression tests for observation-first camera evidence persistence."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from aegis.database.connection import Base
from aegis.database.models import Observation, RiskAssessment
from aegis.database.repositories import ObservationRepository
from aegis.video.camera_sources import FrameIngestionService
import aegis.database.models  # noqa: F401 - register mappings on Base


def test_observations_are_persisted_before_and_linked_to_a_later_event(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'observations.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    @contextmanager
    def session_provider():
        with Session.begin() as session:
            yield session

    import aegis.database.connection as connection

    monkeypatch.setattr(connection, "get_db_session", session_provider)
    service = FrameIngestionService()
    captured_at = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
    payload = {
        "track_id": "north-gate:7",
        "raw_track_id": 7,
        "class_name": "person",
        "confidence": 0.82,
        "bbox": [10, 20, 110, 240],
        "zone_id": "north-gate-zone",
        "zone_name": "North Gate",
        "is_person": True,
        "weapon_track_id": 9,
        "association_type": "contained",
        "association_score": 0.91,
        "risk_level": "HIGH",
        "risk_score": 0.72,
        "verification_status": "confirmed",
        "reason_codes": ["WEAPON_NEAR_PERSON_STABLE"],
        "risk_factors": ["person and weapon proximity"],
        "model_source": ["yolo", "weapon_detector"],
        "behavior_labels": ["normal"],
        "stable_frames": 3,
    }

    service._persist_frame_observations(
        camera_id="north-gate",
        source_epoch="epoch-a",
        frame_id=42,
        captured_at=captured_at,
        track_payloads=[payload],
    )

    assert payload["observation_persistence_status"] == "persisted"
    assert len(payload["observation_ids"]) == 2
    with Session() as session:
        observations = session.query(Observation).order_by(Observation.observation_type).all()
        assert [item.observation_type for item in observations] == [
            "object_person_association",
            "track_detection",
        ]
        relation = next(item for item in observations if item.observation_type == "object_person_association")
        assert relation.related_track_key == "north-gate:9"
        assert relation.event_id is None
        assert relation.observation_metadata["association_type"] == "contained"

    event = {
        "event_id": "evt-observation-link",
        "alert_id": "alert-observation-link",
        "camera_id": "north-gate",
        "track_id": "north-gate:7",
        "timestamp": captured_at.isoformat(),
        "risk_level": "HIGH",
        "risk_score": 0.72,
        "object_class": "person",
        "explanation": "Association requires operator review.",
        "reason": "Association requires operator review.",
        "factors": ["WEAPON_NEAR_PERSON_STABLE"],
        "snapshot_status": "unavailable",
        "observation_ids": payload["observation_ids"],
    }
    assert service._persist_event(event) is True

    with Session() as session:
        linked = ObservationRepository(session).list_for_event("evt-observation-link")
        assert {item.observation_id for item in linked} == set(payload["observation_ids"])
        assert event["incident_id"] is not None
        assessment = session.query(RiskAssessment).one()
        assert assessment.incident_id == event["incident_id"]
        assert assessment.event_id == "evt-observation-link"
        assert assessment.confidence_status == "not_calibrated"
        assert "independent_interaction_signal_missing" in assessment.missing_evidence
    engine.dispose()
