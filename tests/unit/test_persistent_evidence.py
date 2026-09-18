"""Focused Phase 2 tests for durable, keyframe-backed alert evidence."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from aegis.api.security import verify_api_key
from aegis.database.connection import Base
from aegis.database.models import Incident
from aegis.database.repositories import EventRepository
from aegis.video.camera_sources import EventSnapshot, FrameIngestionService
import aegis.database.models  # noqa: F401 - register event mappings


@pytest.fixture()
def evidence_database(tmp_path):
    database_path = tmp_path / "persistent-evidence.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    yield Session, database_path
    engine.dispose()


def _evidence_kwargs(event_id: str, *, level: str = "HIGH") -> dict:
    return {
        "event_id": event_id,
        "event_type": "risk_alert",
        "message": "Confirmed restricted-zone intrusion.",
        "reason": "Confirmed restricted-zone intrusion.",
        "timestamp": datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc),
        "track_id": 17,
        "track_key": "north-gate:17",
        "alert_id": f"alert-{event_id}",
        "camera_id": "north-gate",
        "camera_name": "North Gate",
        "object_class": "person",
        "risk_level": level,
        "risk_score": 0.91 if level == "CRITICAL" else 0.72,
        "factors": ["ZONE_INTRUSION", "CONFIRMED_MULTI_SIGNAL_RISK"],
        "zone": "Restricted Gate",
        "zone_id": "north-gate_zone_0",
        "zone_name": "Restricted Gate",
        "bounding_box": [10, 20, 110, 240],
        "snapshot_path": f"data/output/snapshots/north-gate_{event_id}_20260802T120000000000Z.jpg",
        "snapshot_status": "saved",
        "clip_path": None,
        "metadata": {"source": "test", "reason_codes": ["ZONE_INTRUSION"]},
    }


def test_high_and_critical_evidence_persist_with_snapshot_and_explanation(evidence_database):
    Session, _ = evidence_database
    with Session.begin() as session:
        repository = EventRepository(session)
        high, high_created = repository.create_or_get_evidence(**_evidence_kwargs("evt-high"))
        critical, critical_created = repository.create_or_get_evidence(**_evidence_kwargs("evt-critical", level="CRITICAL"))

        assert high_created and critical_created
        assert high.snapshot_status == "saved"
        assert critical.risk_level == "CRITICAL"

    with Session() as session:
        saved = EventRepository(session).get_by_event_id("evt-high")
        assert saved is not None
        assert saved.snapshot_path.endswith("evt-high_20260802T120000000000Z.jpg")
        assert saved.reason == "Confirmed restricted-zone intrusion."
        assert saved.factors == ["ZONE_INTRUSION", "CONFIRMED_MULTI_SIGNAL_RISK"]
        assert saved.bounding_box == [10, 20, 110, 240]
        assert saved.camera_name == "North Gate"


def test_evidence_is_deduplicated_and_survives_a_new_database_session(evidence_database):
    Session, database_path = evidence_database
    with Session.begin() as session:
        repository = EventRepository(session)
        _, first_created = repository.create_or_get_evidence(**_evidence_kwargs("evt-restart"))
        _, second_created = repository.create_or_get_evidence(**_evidence_kwargs("evt-restart"))
        assert first_created is True
        assert second_created is False

    # Reopen the file-backed database to prove this is not an APIState cache.
    reopened_engine = create_engine(f"sqlite:///{database_path}")
    ReopenedSession = sessionmaker(bind=reopened_engine, expire_on_commit=False)
    with ReopenedSession() as session:
        evidence = EventRepository(session).get_recent_evidence()
        assert [item.event_id for item in evidence] == ["evt-restart"]
    reopened_engine.dispose()


def test_frame_ingestion_persists_one_high_alert_with_all_evidence_fields(monkeypatch, evidence_database):
    Session, _ = evidence_database

    @contextmanager
    def session_provider():
        with Session.begin() as session:
            yield session

    import aegis.database.connection as connection

    monkeypatch.setattr(connection, "get_db_session", session_provider)
    service = FrameIngestionService()
    event = {
        "event_id": "evt-ingestion-high",
        "alert_id": "evt-ingestion-high",
        "event_type": "risk_alert",
        "camera_id": "north-gate",
        "camera_name": "North Gate",
        "track_id": "north-gate:17",
        "timestamp": "2026-08-02T12:00:00+00:00",
        "risk_level": "HIGH",
        "risk_score": 0.72,
        "object_class": "person",
        "bbox": [10, 20, 110, 240],
        "zone_id": "north-gate_zone_0",
        "zone_name": "Restricted Gate",
        "zone": "Restricted Gate",
        "explanation": "Confirmed restricted-zone intrusion.",
        "reason": "Confirmed restricted-zone intrusion.",
        "factors": ["ZONE_INTRUSION", "CONFIRMED_MULTI_SIGNAL_RISK"],
        "snapshot_path": "data/output/snapshots/north-gate_evt-ingestion-high_20260802T120000000000Z.jpg",
        "snapshot_status": "saved",
        "clip_path": None,
    }

    assert service._persist_event(event) is True
    # A retried notification is not a second durable event.
    assert service._persist_event(event) is True
    assert event["evidence_id"] == "evt-ingestion-high"
    assert event["incident_id"] is not None

    with Session() as session:
        saved = EventRepository(session).get_by_event_id("evt-ingestion-high")
        assert saved is not None
        assert saved.alert_id == "evt-ingestion-high"
        assert saved.track_key == "north-gate:17"
        assert saved.zone_id == "north-gate_zone_0"
        assert saved.snapshot_status == "saved"
        assert saved.incident_id == event["incident_id"]
        assert len(EventRepository(session).get_recent_evidence()) == 1


def test_weapon_alert_persists_person_weapon_boxes_and_incident_links(monkeypatch, evidence_database):
    Session, _ = evidence_database

    @contextmanager
    def session_provider():
        with Session.begin() as session:
            yield session

    import aegis.database.connection as connection

    monkeypatch.setattr(connection, "get_db_session", session_provider)
    event = {
        "event_id": "evt-weapon-context",
        "alert_id": "evt-weapon-context",
        "event_type": "risk_alert",
        "threat_event_type": "possible_armed_threat",
        "camera_id": "north-gate",
        "camera_name": "North Gate",
        "track_id": "north-gate:12",
        "person_track_id": "12",
        "weapon_track_id": "30",
        "nearby_person_track_id": "18",
        "related_track_ids": ["north-gate:30", "north-gate:18"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "risk_level": "CRITICAL",
        "risk_score": 0.90,
        "object_class": "person",
        "bbox": [100, 100, 200, 320],
        "explanation": "Possible armed threat. Operator review required.",
        "reason": "Possible armed threat. Operator review required.",
        "factors": ["CRITICAL_WEAPON_AGGRESSION_COMBINATION"],
        "reason_codes": ["CRITICAL_WEAPON_AGGRESSION_COMBINATION"],
        "snapshot_path": "data/output/snapshots/weapon-context.jpg",
        "snapshot_status": "saved",
        "clip_path": None,
        "threat_context": {
            "armed_person_bbox": [100, 100, 200, 320],
            "weapon_bbox": [165, 155, 190, 205],
            "nearby_person_bbox": [225, 100, 325, 320],
            "weapon_class": "knife",
        },
        "evidence_objects": [
            {"object_class": "person", "track_id": "12", "bbox": [100, 100, 200, 320]},
            {"object_class": "knife", "track_id": "30", "bbox": [165, 155, 190, 205]},
            {"object_class": "person", "track_id": "18", "bbox": [225, 100, 325, 320]},
        ],
    }

    assert FrameIngestionService()._persist_event(event) is True

    with Session() as session:
        saved = EventRepository(session).get_by_event_id("evt-weapon-context")
        incident = session.query(Incident).filter_by(incident_id=event["incident_id"]).one()
        assert saved is not None
        assert saved.bounding_box == [100, 100, 200, 320]
        assert saved.event_metadata["threat_context"]["weapon_bbox"] == [165, 155, 190, 205]
        assert saved.event_metadata["threat_context"]["armed_person_bbox"] == [100, 100, 200, 320]
        assert incident.primary_track_id == "north-gate:12"
        assert incident.related_track_ids == ["north-gate:30", "north-gate:18"]


def test_alert_keyframe_uses_safe_compressed_filename(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    result = FrameIngestionService()._save_event_snapshot(
        camera_id="North Gate / 1",
        event_id="evt:high/1",
        timestamp=datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc),
        frame=np.zeros((16, 16, 3), dtype=np.uint8),
    )

    assert result.status == "saved"
    assert result.path is not None
    assert result.path.startswith("data/output/snapshots/North-Gate-1_evt-high-1_")
    assert (tmp_path / result.path).is_file()


def test_snapshot_failure_does_not_break_confirmed_alert_creation(monkeypatch):
    service = FrameIngestionService()
    persisted: list[dict] = []
    alert_manager = SimpleNamespace(
        process_risk=lambda **_kwargs: SimpleNamespace(event_id="evt-snapshot-failed"),
    )
    monkeypatch.setattr(service, "_get_alert_manager", lambda: alert_manager)
    monkeypatch.setattr(service, "_save_event_snapshot", lambda **_kwargs: EventSnapshot(path=None, status="failed"))
    monkeypatch.setattr(service, "_persist_event", lambda event: persisted.append(event) or True)

    payload = {
        "track_id": "north-gate:17",
        "risk_level": "HIGH",
        "risk_score": 0.72,
        "risk_explanation": "Confirmed restricted-zone intrusion.",
        "risk_factors": ["ZONE_INTRUSION"],
        "reason_codes": ["ZONE_INTRUSION"],
        "verification_status": "confirmed",
        "class_name": "person",
        "detected_classes": ["person"],
        "behavior_labels": ["normal"],
        "bbox": [10, 20, 110, 240],
    }
    frame = np.zeros((16, 16, 3), dtype=np.uint8)

    assert service._maybe_generate_alert("north-gate", payload, 1, datetime.now(timezone.utc), frame) is None
    assert service._maybe_generate_alert("north-gate", payload, 2, datetime.now(timezone.utc), frame) is None
    event = service._maybe_generate_alert("north-gate", payload, 3, datetime.now(timezone.utc), frame)

    assert event is not None
    assert event["snapshot_status"] == "failed"
    assert event["snapshot_path"] is None
    assert persisted[0]["event_id"] == "evt-snapshot-failed"


def test_persisted_evidence_api_supports_recent_event_and_alert_lookups(monkeypatch, evidence_database):
    Session, database_path = evidence_database
    monkeypatch.chdir(database_path.parent)
    snapshot = database_path.parent / "data/output/snapshots/north-gate_evt-api_20260802T120000000000Z.jpg"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_bytes(b"\xff\xd8\xff\xd9")
    with Session.begin() as session:
        EventRepository(session).create_or_get_evidence(**_evidence_kwargs("evt-api"))

    @contextmanager
    def session_provider():
        with Session.begin() as session:
            yield session

    import aegis.database.connection as connection
    from aegis.api.routes import events as event_routes

    monkeypatch.setattr(connection, "get_db_session", session_provider)
    monkeypatch.setenv("AEGIS_API_KEY", "evidence-key")
    app = FastAPI()
    app.include_router(event_routes.router, dependencies=[Depends(verify_api_key)])
    client = TestClient(app)

    assert client.get("/events/persisted").status_code == 401
    headers = {"X-API-Key": "evidence-key"}
    recent = client.get("/events/persisted", headers=headers)
    assert recent.status_code == 200
    assert recent.json()["evidence"][0]["snapshot_status"] == "saved"
    assert client.get("/events/evidence/evt-api", headers=headers).status_code == 200
    assert client.get("/events/evidence/alert/alert-evt-api", headers=headers).status_code == 200
    snapshot_response = client.get("/events/evidence/evt-api/snapshot", headers=headers)
    assert snapshot_response.status_code == 200
    assert snapshot_response.headers["content-type"] == "image/jpeg"
