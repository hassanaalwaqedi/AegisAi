"""Durable alert lifecycle tests using the active SQLAlchemy persistence stack."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest


@pytest.fixture
def isolated_database(monkeypatch: pytest.MonkeyPatch, tmp_path):
    from aegis.database import connection

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'alerts.db'}")
    monkeypatch.setattr(connection, "_engine", None)
    monkeypatch.setattr(connection, "_SessionLocal", None)
    connection.create_tables()
    yield connection
    monkeypatch.setattr(connection, "_engine", None)
    monkeypatch.setattr(connection, "_SessionLocal", None)


def test_alert_creation_acknowledgement_and_cooldown_survive_new_manager(isolated_database) -> None:
    from aegis.alerts import AlertChannel, AlertManager, AlertManagerConfig
    from aegis.database.repositories import EventRepository

    with isolated_database.get_db_session() as session:
        EventRepository(session).create_or_get_evidence(
            event_id="evidence-alert-1",
            event_type="risk_alert",
            message="Possible armed threat",
            timestamp=datetime.now(timezone.utc),
            risk_level="HIGH",
            risk_score=0.92,
        )

    config = AlertManagerConfig(
        channels={AlertChannel.API},
        log_to_file=False,
        cooldown_seconds=60.0,
    )
    manager = AlertManager(config=config)
    alert = manager.process_risk(
        track_id=12,
        risk_level="HIGH",
        risk_score=0.92,
        message="Possible armed threat",
        factors=["weapon-person association"],
        cooldown_key="camera-1:armed:12",
    )

    assert alert is not None
    assert manager.persist_alert(alert, event_id="evidence-alert-1", cooldown_key="camera-1:armed:12")

    restarted_manager = AlertManager(config=config)
    persisted = restarted_manager.get_persisted_alerts()
    assert len(persisted) == 1
    assert persisted[0]["alert_id"] == alert.event_id
    assert persisted[0]["delivery_status"] == "queued"
    assert restarted_manager.process_risk(
        track_id=12,
        risk_level="HIGH",
        risk_score=0.92,
        message="Duplicate threat",
        cooldown_key="camera-1:armed:12",
    ) is None

    assert restarted_manager.acknowledge_persisted_alert(alert.event_id)
    assert restarted_manager.get_persisted_alerts(active_only=True) == []
