"""Focused Phase 2 tests for durable, truthful operator data flows."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest


@pytest.fixture
def isolated_database(monkeypatch: pytest.MonkeyPatch, tmp_path):
    from aegis.database import connection

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'phase2.db'}")
    monkeypatch.setattr(connection, "_engine", None)
    monkeypatch.setattr(connection, "_SessionLocal", None)
    connection.create_tables()
    yield connection
    monkeypatch.setattr(connection, "_engine", None)
    monkeypatch.setattr(connection, "_SessionLocal", None)


def test_persisted_alert_exposes_camera_event_incident_and_evidence_links(isolated_database) -> None:
    from aegis.alerts import AlertChannel, AlertManager, AlertManagerConfig
    from aegis.database.repositories import EventRepository

    with isolated_database.get_db_session() as session:
        EventRepository(session).create_or_get_evidence(
            event_id="evidence-phase2-1",
            event_type="risk_alert",
            message="Possible armed threat",
            timestamp=datetime.now(timezone.utc),
            camera_id="cam-3",
            incident_id="incident-phase2-1",
            risk_level="HIGH",
            risk_score=0.91,
            bounding_box=[10, 20, 30, 40],
            snapshot_path="data/output/snapshots/evidence-phase2-1.jpg",
            snapshot_status="saved",
        )

    manager = AlertManager(AlertManagerConfig(channels={AlertChannel.API}, log_to_file=False))
    alert = manager.process_risk(12, "HIGH", 0.91, "Possible armed threat", cooldown_key="cam-3:12")
    assert alert is not None
    assert manager.persist_alert(alert, event_id="evidence-phase2-1", cooldown_key="cam-3:12")

    persisted = manager.get_persisted_alerts()
    assert persisted[0]["camera_id"] == "cam-3"
    assert persisted[0]["event_id"] == "evidence-phase2-1"
    assert persisted[0]["incident_id"] == "incident-phase2-1"
    assert persisted[0]["evidence_id"] == "evidence-phase2-1"
    assert persisted[0]["evidence_status"] == "saved"


def test_persisted_evidence_endpoint_returns_retrievable_snapshot_metadata(isolated_database) -> None:
    from aegis.api.routes.events import get_persisted_evidence
    from aegis.database.repositories import EventRepository

    with isolated_database.get_db_session() as session:
        EventRepository(session).create_or_get_evidence(
            event_id="evidence-phase2-2",
            event_type="risk_alert",
            message="Evidence retained",
            timestamp=datetime.now(timezone.utc),
            snapshot_path="data/output/snapshots/evidence-phase2-2.jpg",
            snapshot_status="saved",
        )

    payload = asyncio.run(get_persisted_evidence(limit=10, level=None))
    assert payload["count"] == 1
    assert payload["evidence"][0]["event_id"] == "evidence-phase2-2"
    assert payload["evidence"][0]["snapshot_available"] is True
    assert payload["evidence"][0]["snapshot_url"].endswith("/evidence-phase2-2/snapshot")


def test_semantic_search_marks_durable_store_unavailable_without_fabricating(monkeypatch: pytest.MonkeyPatch) -> None:
    from aegis.api.routes import semantic
    from aegis.semantic.query_engine import SemanticQueryEngine

    class State:
        def get_events(self, limit: int):
            return []

    monkeypatch.setattr(semantic, "load_persisted_event_records", lambda limit: (_ for _ in ()).throw(RuntimeError("db down")))
    events, storage, reason = semantic._queryable_events(State())
    execution = SemanticQueryEngine().search("find confirmed people carrying weapons", tracks=[], events=events, statistics={})

    assert storage == "unavailable"
    assert reason
    assert execution.results == []


def test_agent_refuses_operational_answer_when_required_source_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    import aegis.ai.orchestrator as orchestrator_module
    from aegis.ai.orchestrator import AIOrchestrator
    from aegis.ai.schemas import ChatRequest

    monkeypatch.setattr(
        orchestrator_module,
        "collect_system_context",
        lambda *args, **kwargs: {"active_alerts": {"availability": "unavailable", "reason": "database unavailable"}},
    )
    monkeypatch.setattr(orchestrator_module, "context_to_text", lambda context: "UNAVAILABLE")
    monkeypatch.setattr(
        orchestrator_module,
        "get_system_knowledge_service",
        lambda: SimpleNamespace(retrieve=lambda *args, **kwargs: SimpleNamespace(is_official_question=False)),
    )

    class Provider:
        def generate_json(self, **kwargs):  # pragma: no cover - must not be called
            raise AssertionError("provider must not be called for unavailable operational data")

    response = AIOrchestrator(provider=Provider()).process(ChatRequest(message="show high risk alerts"))
    assert response.confidence == 1.0
    assert "couldn't verify" in response.answer.lower()
    assert response.error == "database unavailable"


def test_idle_websocket_sends_heartbeat_instead_of_empty_simulated_update() -> None:
    from aegis.api.websocket import build_live_state_message

    state = SimpleNamespace(
        get_status=lambda: {"running": True},
        get_tracks=lambda: [],
        get_events=lambda limit: [],
        get_statistics=lambda: {"should_not": "be included"},
    )
    message = build_live_state_message(state)

    assert message["type"] == "heartbeat"
    assert message["status"] == {"running": True}
    assert "tracks" not in message
    assert "events" not in message


def test_readiness_reports_missing_detector_weights_as_unavailable(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from fastapi import Response
    import config
    from aegis.api.routes import health
    from aegis.database import connection
    from aegis.api.routes import cameras

    class DetectionConfig:
        model_path = str(tmp_path / "missing-base.pt")
        weapon_model_path = str(tmp_path / "missing-weapon.pt")

    monkeypatch.setattr(config, "DetectionConfig", DetectionConfig)
    monkeypatch.setattr(health, "api_authentication_readiness", lambda: (True, "configured"))
    monkeypatch.setattr(connection, "check_connection", lambda: True)
    monkeypatch.setattr(
        cameras,
        "get_camera_manager",
        lambda: SimpleNamespace(list_cameras=lambda: []),
    )

    response = Response()
    payload = asyncio.run(health.readiness(response))

    assert response.status_code == 503
    assert payload["status"] == "not_ready"
    assert payload["checks"]["base_detector"]["status"] == "error"
    assert payload["checks"]["weapon_detector"]["status"] == "warning"
