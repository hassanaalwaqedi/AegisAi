"""Focused Phase 3 checks for durable lifecycle and audit guarantees."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from aegis.ai.language import ResponseLanguage, detect_response_language
from aegis.ai.routes import _audit_agent_request
from aegis.ai.schemas import ChatResponse, Intent
from aegis.alerts import AlertManager
from aegis.api.routes import alerts as alert_routes
from aegis.api.routes import events as event_routes
from aegis.api.security import verify_api_key
from aegis.database.connection import Base
from aegis.database.models import AuditLog
from aegis.database.repositories import AuditLogRepository, EventRepository, IncidentRepository, OperationalAlertRepository
from aegis.intelligence.incident_correlation import IncidentCorrelationService
import aegis.database.models  # noqa: F401 - register all mapped tables


def _session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'phase3.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    return Session, engine


def _event(event_id: str, observed_at: datetime, *, risk: str = "HIGH") -> dict:
    return {
        "event_id": event_id,
        "alert_id": f"alert-{event_id}",
        "event_type": "person_weapon_association",
        "message": "Possible weapon-person association requires operator review.",
        "reason": "Possible weapon-person association requires operator review.",
        "timestamp": observed_at,
        "camera_id": "camera-3",
        "camera_name": "Camera 3",
        "track_key": "camera-3:12",
        "track_id": 12,
        "risk_level": risk,
        "risk_score": 0.91,
        "factors": ["weapon-person association", "second person nearby"],
        "zone_id": "camera-3:entrance",
        "zone_name": "Entrance",
        "snapshot_status": "unavailable",
        "metadata": {"nearby_person_track_id": "camera-3:21"},
    }


def test_incident_lifecycle_preserves_operator_review_and_fact_only_summary(tmp_path):
    Session, engine = _session_factory(tmp_path)
    observed_at = datetime.now(timezone.utc)
    try:
        with Session.begin() as session:
            first, _ = EventRepository(session).create_or_get_evidence(**_event("evt-phase3-1", observed_at))
            service = IncidentCorrelationService(session, now=lambda: observed_at)
            incident = service.correlate_event(first)
            assert incident is not None

            updated = IncidentRepository(session).set_lifecycle_status(
                incident.incident_id,
                "under_review",
                actor_id="operator-17",
                reason="Reviewing saved evidence.",
            )
            assert updated is not None
            assert updated.to_dict()["status"] == "under_review"
            assert updated.to_dict()["processing_status"] == "active"
            assert "camera-3" in updated.to_dict()["summary"]
            assert "1 event(s)" in updated.to_dict()["summary"]

            second, _ = EventRepository(session).create_or_get_evidence(
                **_event("evt-phase3-2", observed_at + timedelta(seconds=30), risk="CRITICAL")
            )
            correlated = IncidentCorrelationService(
                session, now=lambda: observed_at + timedelta(seconds=30)
            ).correlate_event(second)
            assert correlated is not None
            assert correlated.incident_id == incident.incident_id
            assert correlated.lifecycle_status == "under_review"
            assert correlated.risk_types == ["person_weapon_association"]
    finally:
        engine.dispose()


def test_operator_actions_and_agent_queries_create_non_sensitive_audit_records(monkeypatch, tmp_path):
    Session, engine = _session_factory(tmp_path)
    observed_at = datetime.now(timezone.utc)
    try:
        with Session.begin() as session:
            event, _ = EventRepository(session).create_or_get_evidence(**_event("evt-phase3-api", observed_at))
            incident = IncidentCorrelationService(session, now=lambda: observed_at).correlate_event(event)
            assert incident is not None
            incident_id = incident.incident_id

        @contextmanager
        def session_provider():
            with Session.begin() as session:
                yield session

        import aegis.database.connection as connection

        monkeypatch.setattr(connection, "get_db_session", session_provider)
        monkeypatch.setenv("AEGIS_API_KEY", "phase3-key")
        app = FastAPI()
        app.include_router(event_routes.router, dependencies=[Depends(verify_api_key)])
        client = TestClient(app)
        headers = {"X-API-Key": "phase3-key", "X-Aegis-Actor": "operator-17"}

        response = client.patch(
            f"/events/incidents/{incident_id}/status",
            headers=headers,
            json={"status": "acknowledged", "reason": "Operator accepted the queue item."},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "acknowledged"

        evidence = client.get(f"/events/evidence/{event.event_id}", headers=headers)
        assert evidence.status_code == 200

        _audit_agent_request(
            ChatResponse(intent=Intent.RISK, response_language=ResponseLanguage.ARABIC),
            actor="operator-17",
            voice_mode=True,
        )
        with Session() as session:
            actions = {row.action for row in AuditLogRepository(session).list_recent()}
            assert {"incident.lifecycle_changed", "evidence.record_accessed", "agent.operational_query"}.issubset(actions)
            details = session.query(AuditLog).filter(AuditLog.action == "agent.operational_query").one().details
            assert "message" not in details
            assert details["response_language"] == "Arabic"
    finally:
        engine.dispose()


def test_alert_acknowledgement_is_audited_and_language_selection_stays_local(monkeypatch, tmp_path):
    Session, engine = _session_factory(tmp_path)
    observed_at = datetime.now(timezone.utc)
    try:
        with Session.begin() as session:
            event, _ = EventRepository(session).create_or_get_evidence(**_event("evt-phase3-alert", observed_at))
            OperationalAlertRepository(session).create_or_get(
                alert_id="alert-phase3",
                event_id=event.event_id,
                event_record_id=event.id,
                track_id="camera-3:12",
                level="HIGH",
                risk_score=0.91,
                message=event.message,
                zone="Entrance",
                factors=["weapon-person association"],
                cooldown_key="camera-3:12",
                cooldown_expires_at=observed_at + timedelta(minutes=1),
                delivery_status="created",
                delivery_attempts=0,
                delivered_at=None,
                last_delivery_error=None,
            )

        @contextmanager
        def session_provider():
            with Session.begin() as session:
                yield session

        import aegis.database.connection as connection

        monkeypatch.setattr(connection, "get_db_session", session_provider)
        monkeypatch.setenv("AEGIS_API_KEY", "phase3-key")
        alert_routes.set_alert_manager(AlertManager())
        app = FastAPI()
        app.include_router(alert_routes.router)
        client = TestClient(app)
        response = client.post(
            "/alerts/alert-phase3/acknowledge",
            headers={"X-API-Key": "phase3-key", "X-Aegis-Actor": "operator-17"},
        )
        assert response.status_code == 200
        with Session() as session:
            audit = session.query(AuditLog).filter(AuditLog.action == "alert.acknowledged").one()
            assert audit.actor_id == "operator-17"

        assert detect_response_language("هناك high risk alert؟") == ResponseLanguage.ARABIC
        assert detect_response_language("What happened in camera 3?") == ResponseLanguage.ENGLISH
        assert detect_response_language("Kamera üç aktif mi?") == ResponseLanguage.TURKISH
    finally:
        engine.dispose()
