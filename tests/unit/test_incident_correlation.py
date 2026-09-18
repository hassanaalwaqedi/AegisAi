"""Focused Phase 3 tests for durable event-to-incident correlation."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from aegis.api.security import verify_api_key
from aegis.database.connection import Base
from aegis.database.repositories import EventRepository, IncidentRepository
from aegis.intelligence.incident_correlation import IncidentCorrelationService
from aegis.video.camera_sources import FrameIngestionService
import aegis.database.models  # noqa: F401 - register mapped tables


BASE_TIME = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def incident_database(tmp_path):
    database_path = tmp_path / "incidents.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    yield Session
    engine.dispose()


def _event_kwargs(
    event_id: str,
    *,
    timestamp: datetime = BASE_TIME,
    camera_id: str = "north-gate",
    track_key: str = "north-gate:17",
    zone_id: str | None = "north-gate:restricted",
    level: str = "HIGH",
    score: float = 0.72,
    event_type: str = "restricted_zone",
    reason: str = "Track entered the restricted zone.",
) -> dict:
    return {
        "event_id": event_id,
        "event_type": event_type,
        "message": reason,
        "reason": reason,
        "timestamp": timestamp,
        "track_id": 17,
        "track_key": track_key,
        "alert_id": f"alert-{event_id}",
        "camera_id": camera_id,
        "camera_name": "North Gate" if camera_id == "north-gate" else "South Gate",
        "object_class": "person",
        "risk_level": level,
        "risk_score": score,
        "factors": ["ZONE_INTRUSION"] if event_type == "restricted_zone" else ["LOITERING"],
        "zone": "Restricted Gate" if zone_id else None,
        "zone_id": zone_id,
        "zone_name": "Restricted Gate" if zone_id else None,
        "bounding_box": [10, 20, 100, 200],
        "snapshot_path": None,
        "snapshot_status": "unavailable",
        "clip_path": None,
        "metadata": {"reason_codes": ["ZONE_INTRUSION"]},
    }


def _persist_and_correlate(session, event_id: str, **kwargs):
    event, created = EventRepository(session).create_or_get_evidence(
        **_event_kwargs(event_id, **kwargs)
    )
    incident = IncidentCorrelationService(session, now=lambda: BASE_TIME).correlate_event(event)
    return event, incident, created


def test_same_track_restricted_zone_and_loitering_form_one_incident(incident_database):
    Session = incident_database
    with Session.begin() as session:
        first_event, first_incident, _ = _persist_and_correlate(session, "evt-zone")
        second_event, second_incident, _ = _persist_and_correlate(
            session,
            "evt-loiter",
            timestamp=BASE_TIME + timedelta(minutes=2),
            event_type="loitering",
            reason="Track remained in the restricted zone.",
        )

        assert first_incident is not None
        assert second_incident is not None
        assert first_incident.incident_id == second_incident.incident_id
        assert first_event.incident_id == second_incident.incident_id
        assert second_event.incident_id == second_incident.incident_id
        assert second_incident.event_ids == ["evt-zone", "evt-loiter"]
        assert second_incident.evidence_ids == ["evt-zone", "evt-loiter"]
        assert {"ZONE_INTRUSION", "LOITERING"}.issubset(second_incident.contributing_factors)


def test_high_critical_alert_attaches_evidence_and_preserves_peak_risk(incident_database):
    Session = incident_database
    with Session.begin() as session:
        _, incident, _ = _persist_and_correlate(session, "evt-high")
        _, updated, _ = _persist_and_correlate(
            session,
            "evt-critical",
            timestamp=BASE_TIME + timedelta(minutes=1),
            level="CRITICAL",
            score=0.94,
            event_type="person_weapon_association",
            reason="Stable person-weapon association requires review.",
        )

        assert incident is not None and updated is not None
        assert updated.incident_id == incident.incident_id
        assert updated.current_risk_level == "CRITICAL"
        assert updated.max_risk_score == pytest.approx(0.94)
        assert updated.alert_ids == ["alert-evt-high", "alert-evt-critical"]
        assert updated.evidence_ids == ["evt-high", "evt-critical"]


def test_duplicate_event_does_not_create_duplicate_incident(incident_database):
    Session = incident_database
    with Session.begin() as session:
        event, incident, created = _persist_and_correlate(session, "evt-duplicate")
        second_incident = IncidentCorrelationService(session, now=lambda: BASE_TIME).correlate_event(event)

        assert created is True
        assert incident is not None and second_incident is not None
        assert incident.incident_id == second_incident.incident_id
        assert IncidentRepository(session).active_count() == 1
        assert incident.event_ids == ["evt-duplicate"]


def test_unrelated_track_or_camera_creates_a_separate_incident(incident_database):
    Session = incident_database
    with Session.begin() as session:
        _, first, _ = _persist_and_correlate(session, "evt-north")
        _, different_track, _ = _persist_and_correlate(
            session,
            "evt-different-track",
            track_key="north-gate:88",
            zone_id=None,
            timestamp=BASE_TIME + timedelta(minutes=1),
        )
        _, different_camera, _ = _persist_and_correlate(
            session,
            "evt-south",
            camera_id="south-gate",
            track_key="south-gate:17",
            zone_id="south-gate:restricted",
            timestamp=BASE_TIME + timedelta(minutes=1),
        )

        assert first is not None and different_track is not None and different_camera is not None
        assert len({first.incident_id, different_track.incident_id, different_camera.incident_id}) == 3


def test_incident_resolves_after_idle_timeout(incident_database):
    Session = incident_database
    with Session.begin() as session:
        _, incident, _ = _persist_and_correlate(session, "evt-idle")
        assert incident is not None
        resolver = IncidentCorrelationService(session, now=lambda: BASE_TIME + timedelta(minutes=6))
        assert resolver.resolve_expired() == 1
        assert incident.status == "resolved"


def test_correlation_failure_keeps_durable_alert_evidence_and_pipeline_running(monkeypatch, incident_database):
    Session = incident_database

    @contextmanager
    def session_provider():
        with Session.begin() as session:
            yield session

    import aegis.database.connection as connection
    from aegis.intelligence import incident_correlation

    monkeypatch.setattr(connection, "get_db_session", session_provider)
    monkeypatch.setattr(
        incident_correlation.IncidentCorrelationService,
        "correlate_event",
        lambda _self, _event: (_ for _ in ()).throw(RuntimeError("incident write unavailable")),
    )
    event = {
        "event_id": "evt-correlation-failure",
        "alert_id": "alert-evt-correlation-failure",
        "camera_id": "north-gate",
        "camera_name": "North Gate",
        "track_id": "north-gate:17",
        "timestamp": BASE_TIME.isoformat(),
        "risk_level": "HIGH",
        "risk_score": 0.72,
        "object_class": "person",
        "zone_id": "north-gate:restricted",
        "zone_name": "Restricted Gate",
        "zone": "Restricted Gate",
        "explanation": "Confirmed restricted-zone intrusion.",
        "reason": "Confirmed restricted-zone intrusion.",
        "factors": ["ZONE_INTRUSION"],
        "snapshot_path": None,
        "snapshot_status": "unavailable",
        "clip_path": None,
    }

    assert FrameIngestionService()._persist_event(event) is True
    with Session() as session:
        assert EventRepository(session).get_by_event_id("evt-correlation-failure") is not None


def test_incident_api_returns_active_timeline_and_evidence(monkeypatch, incident_database):
    Session = incident_database
    with Session.begin() as session:
        _, incident, _ = _persist_and_correlate(session, "evt-api-incident")
        assert incident is not None
        incident_id = incident.incident_id

    @contextmanager
    def session_provider():
        with Session.begin() as session:
            yield session

    import aegis.database.connection as connection
    from aegis.api.routes import events as event_routes

    monkeypatch.setattr(connection, "get_db_session", session_provider)
    monkeypatch.setenv("AEGIS_API_KEY", "incident-key")
    app = FastAPI()
    app.include_router(event_routes.router, dependencies=[Depends(verify_api_key)])
    client = TestClient(app)
    headers = {"X-API-Key": "incident-key"}

    assert client.get("/events/incidents").status_code == 401
    active = client.get("/events/incidents", headers=headers)
    assert active.status_code == 200
    assert active.json()["incidents"][0]["incident_id"] == incident_id
    timeline = client.get(f"/events/incidents/{incident_id}/timeline", headers=headers)
    assert timeline.status_code == 200
    assert timeline.json()["events"][0]["event_id"] == "evt-api-incident"
    evidence = client.get(f"/events/incidents/{incident_id}/evidence", headers=headers)
    assert evidence.status_code == 200
    assert evidence.json()["evidence"][0]["incident_id"] == incident_id
    assessments = client.get(f"/events/incidents/{incident_id}/assessments", headers=headers)
    assert assessments.status_code == 200
    assert assessments.json()["count"] == 0
