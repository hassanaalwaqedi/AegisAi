"""Failure-contract tests for the Phase 0 Intelligence context endpoint."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List

from fastapi.testclient import TestClient

from aegis.intelligence.context_schemas import Availability, IntelligenceContext
from aegis.intelligence.context_service import IntelligenceContextService, _EvidenceValidator


NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)


class FakeState:
    def __init__(
        self,
        *,
        events: List[Dict[str, Any]] | None = None,
        tracks: List[Dict[str, Any]] | None = None,
        statistics: Dict[str, Any] | None = None,
        semantic_engine: Any = None,
    ) -> None:
        self._events = events if events is not None else []
        self._tracks = tracks if tracks is not None else []
        self._statistics = statistics if statistics is not None else {}
        self.semantic_query_engine = semantic_engine
        self.active_semantic_query = None

    def get_events(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self._events[-limit:]

    def get_tracks(self) -> List[Dict[str, Any]]:
        return self._tracks

    def get_statistics(self) -> Dict[str, Any]:
        return self._statistics


class FakeCameraManager:
    def __init__(
        self,
        cameras: List[Dict[str, Any]] | None = None,
        ingestion: Any = None,
    ) -> None:
        self.cameras = cameras if cameras is not None else []
        self.ingestion = ingestion

    def list_cameras(self) -> List[Dict[str, Any]]:
        return self.cameras


class FakeBus:
    def __init__(self, connected: bool) -> None:
        self.is_connected = connected


class FakePersistenceTelemetry:
    def __init__(self, **snapshot: Any) -> None:
        self._snapshot = snapshot

    def snapshot(self) -> Dict[str, Any]:
        return dict(self._snapshot)


def _service(
    *,
    state: FakeState | None = None,
    cameras: List[Dict[str, Any]] | None = None,
    pipeline: Any = None,
    database_connected: bool = True,
    redis_connected: bool = True,
    persistence: Dict[str, Any] | None = None,
    persistence_ready: tuple[bool, str | None] = (True, None),
    durable_events: List[Dict[str, Any]] | None = None,
) -> IntelligenceContextService:
    return IntelligenceContextService(
        state_getter=lambda: state or FakeState(),
        camera_manager_getter=lambda: FakeCameraManager(cameras),
        pipeline_getter=lambda: pipeline,
        event_bus_getter=lambda: FakeBus(redis_connected),
        database_check=lambda: database_connected,
        persistence_status_getter=lambda: FakePersistenceTelemetry(
            **(persistence or {"attempted": 0})
        ),
        persistence_readiness_check=lambda: persistence_ready,
        settings_getter=lambda: SimpleNamespace(gemini=SimpleNamespace(api_key="")),
        incident_snapshot_getter=lambda _observed_at: (0, None),
        durable_events_getter=lambda _limit: list(durable_events or []),
        now=lambda: NOW,
    )


def _check(context: IntelligenceContext, name: str):
    return next(item for item in context.overall.checks if item.name == name)


def test_pipeline_unavailable_is_not_presented_as_healthy() -> None:
    context = _service(pipeline=None).build()

    assert context.pipeline.running is None
    assert context.pipeline.freshness.status == Availability.UNAVAILABLE
    assert _check(context, "pipeline").status == Availability.UNAVAILABLE
    assert _check(context, "model").status == Availability.UNAVAILABLE
    assert any("Pipeline has not been initialized" in reason for reason in context.overall.degraded_reasons)


def test_active_camera_ingestion_model_is_preferred_over_an_idle_worker_detector() -> None:
    """The active camera path must not be masked by an unused worker stage."""
    pipeline = SimpleNamespace(
        _running=True,
        _stages=[
            SimpleNamespace(
                name="detection",
                _running=True,
                _errors=0,
                _detector=None,
            )
        ],
    )
    camera_manager = FakeCameraManager(ingestion=SimpleNamespace(_detector=object()))
    service = IntelligenceContextService(
        state_getter=FakeState,
        camera_manager_getter=lambda: camera_manager,
        pipeline_getter=lambda: pipeline,
        event_bus_getter=lambda: FakeBus(True),
        database_check=lambda: True,
        persistence_status_getter=lambda: FakePersistenceTelemetry(attempted=1, succeeded=1),
        settings_getter=lambda: SimpleNamespace(gemini=SimpleNamespace(api_key="")),
        incident_snapshot_getter=lambda _observed_at: (0, None),
        durable_events_getter=lambda _limit: [],
        now=lambda: NOW,
    )

    context = service.build()

    assert _check(context, "pipeline").status == Availability.LIVE
    assert _check(context, "model").status == Availability.LIVE
    assert "Detection model has not loaded yet." not in context.overall.degraded_reasons


def test_database_unavailable_has_no_fabricated_value() -> None:
    context = _service(database_connected=False).build()

    database = _check(context, "database")
    assert database.status == Availability.OFFLINE
    assert database.detail == "Database connection check returned unavailable."
    assert context.overall.status == Availability.DEGRADED


def test_redis_unavailable_reports_process_local_fallback() -> None:
    context = _service(redis_connected=False).build()

    assert _check(context, "redis").status == Availability.DEGRADED
    assert _check(context, "event_stream").status == Availability.DEGRADED
    assert "process-local fallback" in (_check(context, "redis").detail or "")


def test_no_cameras_is_a_source_backed_zero() -> None:
    context = _service(cameras=[]).build()

    assert context.cameras.total == 0
    assert context.cameras.total_configured == 0
    assert context.cameras.online == 0
    assert context.cameras.offline == 0
    assert context.cameras.stale == 0
    assert context.cameras.unavailable == 0
    assert context.cameras.freshness.status == Availability.LIVE


def test_context_does_not_pad_suggestions_without_evidence() -> None:
    context = _service(cameras=[], state=FakeState()).build()

    assert context.suggestions == []
    serialized = context.model_dump_json(by_alias=True)
    assert "Export daily report" not in serialized
    assert "Search security events" not in serialized


def test_context_marks_runtime_evidence_as_server_validated() -> None:
    """Context citations must match the source snapshot before they are emitted."""
    context = _service(
        state=FakeState(
            events=[
                {
                    "event_id": "alert-1",
                    "type": "risk_alert",
                    "camera_id": "cam-1",
                    "timestamp": NOW.isoformat(),
                    "risk_level": "HIGH",
                    "explanation": "Confirmed high-risk event",
                }
            ],
            tracks=[
                {
                    "track_id": "track-1",
                    "class_name": "Person",
                    "camera_id": "cam-1",
                    "last_updated": NOW.isoformat(),
                }
            ],
        ),
        cameras=[
            {
                "camera_id": "cam-1",
                "name": "Camera 1",
                "runtime": {"status": "online", "last_frame_time": NOW.isoformat()},
            }
        ],
    ).build()

    evidence = [
        *context.events[0].evidence,
        *context.alerts.items[0].evidence,
        *context.tracks[0].evidence,
    ]
    assert evidence
    assert all(reference.server_validated for reference in evidence)
    assert all(reference.validated_at == NOW for reference in evidence)
    assert context.ai.evidence_grounding == Availability.LIVE
    assert not any("not server-validated" in reason for reason in context.overall.degraded_reasons)

    payload = context.model_dump(by_alias=True, mode="json")
    assert payload["events"][0]["evidence"][0]["serverValidated"] is True
    assert datetime.fromisoformat(
        payload["events"][0]["evidence"][0]["validatedAt"].replace("Z", "+00:00")
    ) == NOW


def test_invalid_evidence_reference_is_omitted_and_degrades_grounding() -> None:
    validator = _EvidenceValidator(NOW)
    validator.register_events(
        [
            {
                "event_id": "event-1",
                "camera_id": "camera-1",
                "timestamp": NOW.isoformat(),
            }
        ]
    )

    reference = validator.evidence(
        kind="event",
        item_id="event-1",
        camera_id="different-camera",
        occurred_at=NOW,
        label="runtime event",
    )

    assert reference is None
    assert validator.status == Availability.DEGRADED
    assert validator.reason is not None


def test_offline_and_stale_cameras_are_separated_from_unavailable() -> None:
    context = _service(
        cameras=[
            {
                "camera_id": "offline-cam",
                "name": "Offline Camera",
                "runtime": {"status": "offline", "last_frame_time": None},
            },
            {
                "camera_id": "stale-cam",
                "name": "Stale Camera",
                "runtime": {
                    "status": "online",
                    "last_frame_time": (NOW - timedelta(seconds=30)).isoformat(),
                },
            },
            {
                "camera_id": "unknown-cam",
                "name": "Unknown Camera",
                "runtime": {},
            },
        ]
    ).build()

    assert context.cameras.total == 3
    assert context.cameras.online == 0
    assert context.cameras.offline == 1
    assert context.cameras.stale == 1
    assert context.cameras.unavailable == 1
    runtime_by_id = {item.camera_id: item.runtime for item in context.cameras.items}
    assert runtime_by_id == {
        "offline-cam": Availability.OFFLINE,
        "stale-cam": Availability.STALE,
        "unknown-cam": Availability.UNAVAILABLE,
    }


def test_old_event_and_alert_freshness_uses_their_source_timestamp() -> None:
    event_timestamp = NOW - timedelta(minutes=5)
    context = _service(
        state=FakeState(
            events=[
                {
                    "event_id": "old-alert",
                    "type": "risk_alert",
                    "timestamp": event_timestamp.isoformat(),
                    "risk_level": "HIGH",
                    "explanation": "Source-backed historical alert",
                }
            ]
        )
    ).build()

    assert context.events[0].freshness.observed_at == event_timestamp
    assert context.events[0].freshness.observed_at != context.generated_at
    assert context.events[0].freshness.status == Availability.STALE
    # Historical evidence remains in the event history, but old alerts must
    # not be surfaced as active operator work or spoken again.
    assert context.alerts.items == []
    assert context.alerts.active_count == 0
    assert context.alerts.freshness.observed_at == NOW
    assert context.alerts.freshness.status == Availability.LIVE


def test_context_merges_durable_evidence_with_runtime_alerts_by_public_event_id() -> None:
    context = _service(
        state=FakeState(
            events=[
                {
                    "event_id": "alert-shared",
                    "type": "risk_alert",
                    "timestamp": NOW.isoformat(),
                    "risk_level": "HIGH",
                    "explanation": "Runtime acknowledgement state is current.",
                    "acknowledged": False,
                }
            ]
        ),
        durable_events=[
            {
                "event_id": "alert-durable",
                "type": "risk_alert",
                "timestamp": NOW.isoformat(),
                "risk_level": "CRITICAL",
                "description": "Durable weapon-risk evidence.",
                "evidence_status": "persisted",
            },
            {
                "event_id": "alert-shared",
                "type": "risk_alert",
                "timestamp": NOW.isoformat(),
                "risk_level": "HIGH",
                "description": "Older durable copy.",
                "evidence_status": "persisted",
            },
        ],
    ).build()

    assert {event.event_id for event in context.events} == {"alert-durable", "alert-shared"}
    assert {alert.alert_id for alert in context.alerts.items} == {"alert-durable", "alert-shared"}
    assert context.alerts.active_count == 2
    assert context.alerts.freshness.status == Availability.LIVE


def test_persistence_failure_is_an_explicit_degraded_reason() -> None:
    context = _service(
        persistence={
            "attempted": 1,
            "succeeded": 0,
            "failed": 1,
            "last_failure_at": NOW,
            "last_failure_reason": "database write rejected",
            "last_source": "pipeline_alerting",
        }
    ).build()

    persistence = _check(context, "persistence")
    assert persistence.status == Availability.DEGRADED
    assert "database write rejected" in (persistence.detail or "")
    assert any("Latest durable event write failed" in reason for reason in context.overall.degraded_reasons)


def test_persistence_readiness_is_live_without_creating_a_synthetic_risk_alert() -> None:
    context = _service(persistence={"attempted": 0}, persistence_ready=(True, None)).build()

    persistence = _check(context, "persistence")
    assert persistence.status == Availability.LIVE
    assert "ready" in (persistence.detail or "").lower()
    assert not any("No durable event write" in reason for reason in context.overall.degraded_reasons)


def test_failed_persistence_readiness_is_explicitly_unavailable() -> None:
    context = _service(
        persistence={"attempted": 0},
        persistence_ready=(False, "Database-backed event persistence readiness failed: OperationalError."),
    ).build()

    persistence = _check(context, "persistence")
    assert persistence.status == Availability.UNAVAILABLE
    assert "OperationalError" in (persistence.detail or "")


def test_persistence_readiness_probe_rolls_back_its_internal_record(monkeypatch) -> None:
    from aegis.database import connection, persistence, repositories

    captured: Dict[str, Any] = {}

    class Savepoint:
        rolled_back = False

        def rollback(self):
            self.rolled_back = True

    savepoint = Savepoint()

    class Session:
        def begin_nested(self):
            return savepoint

        def flush(self):
            captured["flushed"] = True

    class SessionContext:
        def __enter__(self):
            return Session()

        def __exit__(self, exc_type, exc, traceback):
            return False

    class RecordingRepository:
        def __init__(self, session: Any):
            captured["session"] = session

        def create(self, **kwargs: Any):
            captured.update(kwargs)

    monkeypatch.setattr(connection, "get_db_session", lambda: SessionContext())
    monkeypatch.setattr(repositories, "EventRepository", RecordingRepository)

    ready, reason = persistence.check_event_persistence_ready()

    assert ready and reason is None
    assert captured["event_type"] == "persistence_readiness_probe"
    assert captured["metadata"] == {"internal": True}
    assert captured["flushed"]
    assert savepoint.rolled_back


def test_alerting_stage_enters_the_active_database_session_and_uses_idempotent_evidence_create(monkeypatch) -> None:
    """Regression test for the old ``create_event``/un-entered-session bug."""
    from aegis.database import connection, repositories
    from aegis.database.persistence import get_persistence_status, reset_persistence_status
    from aegis.pipeline.alerting import AlertingStage

    captured: Dict[str, Any] = {}

    class SessionContext:
        entered = False
        exited = False

        def __enter__(self):
            self.entered = True
            return object()

        def __exit__(self, exc_type, exc, traceback):
            self.exited = True
            return False

    session_context = SessionContext()

    class RecordingRepository:
        def __init__(self, session: Any) -> None:
            captured["session"] = session

        def create_or_get_evidence(self, **kwargs: Any) -> tuple[object, bool]:
            captured.update(kwargs)
            return object(), True

    reset_persistence_status()
    monkeypatch.setattr(connection, "get_db_session", lambda: session_context)
    monkeypatch.setattr(repositories, "EventRepository", RecordingRepository)

    AlertingStage()._persist_event(
        {
            "timestamp": NOW.isoformat(),
            "camera_id": "cam-1",
            "track_id": "track:7",
            "risk_level": "HIGH",
            "risk_score": 0.8,
            "explanation": "Confirmed high-risk condition",
        }
    )

    assert session_context.entered and session_context.exited
    assert captured["event_type"] == "risk_alert"
    assert captured["track_id"] == 7
    assert captured["metadata"]["camera_id"] == "cam-1"
    assert get_persistence_status().snapshot()["succeeded"] == 1
    reset_persistence_status()


def test_alerting_stage_persistence_failure_is_recorded(monkeypatch) -> None:
    from aegis.database import connection, repositories
    from aegis.database.persistence import get_persistence_status, reset_persistence_status
    from aegis.pipeline.alerting import AlertingStage

    class SessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, traceback):
            return False

    class FailingRepository:
        def __init__(self, session: Any) -> None:
            del session

        def create_or_get_evidence(self, **kwargs: Any) -> tuple[object, bool]:
            del kwargs
            raise RuntimeError("write rejected")

    reset_persistence_status()
    monkeypatch.setattr(connection, "get_db_session", lambda: SessionContext())
    monkeypatch.setattr(repositories, "EventRepository", FailingRepository)

    AlertingStage()._persist_event(
        {
            "timestamp": NOW.isoformat(),
            "camera_id": "cam-1",
            "risk_level": "HIGH",
            "risk_score": 0.8,
            "explanation": "Confirmed high-risk condition",
        }
    )

    snapshot = get_persistence_status().snapshot()
    assert snapshot["failed"] == 1
    assert "write rejected" in (snapshot["last_failure_reason"] or "")
    reset_persistence_status()


def test_recent_events_enters_database_session_before_constructing_repository(monkeypatch) -> None:
    """Regression test for passing ``get_db_session()`` itself to a repository."""
    from aegis.ai.tools import get_recent_events
    from aegis.database import connection, repositories
    import aegis.pipeline.startup as startup

    captured: Dict[str, Any] = {}
    session = object()

    class SessionContext:
        entered = False

        def __enter__(self):
            self.entered = True
            return session

        def __exit__(self, exc_type, exc, traceback):
            return False

    session_context = SessionContext()

    class RecordingRepository:
        def __init__(self, received_session: Any) -> None:
            captured["session"] = received_session

        def get_recent(self, limit: int):
            captured["limit"] = limit
            return [
                SimpleNamespace(
                    id=11,
                    event_type="risk_alert",
                    event_metadata={"camera_id": "cam-1"},
                    zone=None,
                    timestamp=NOW,
                    created_at=NOW,
                    risk_level="HIGH",
                    risk_score=0.8,
                    message="Confirmed risk alert",
                )
            ]

    monkeypatch.setattr(startup, "get_alerting_stage", lambda: None)
    monkeypatch.setattr(connection, "get_db_session", lambda: session_context)
    monkeypatch.setattr(repositories, "EventRepository", RecordingRepository)

    events = get_recent_events(limit=3)

    assert session_context.entered
    assert captured == {"session": session, "limit": 3}
    assert events == [
        {
            "id": "11",
            "event_id": "11",
            "type": "risk_alert",
            "event_type": "risk_alert",
            "camera_id": "cam-1",
            "timestamp": NOW.isoformat(),
            "risk_level": "HIGH",
            "risk_score": 0.8,
            "message": "Confirmed risk alert",
            "data": {"camera_id": "cam-1"},
        }
    ]


def test_schema_contract_uses_camel_case_and_endpoint_validates_response(monkeypatch) -> None:
    service = _service(
        state=FakeState(
            events=[
                {
                    "event_id": "alert-1",
                    "type": "risk_alert",
                    "camera_id": "cam-1",
                    "timestamp": NOW.isoformat(),
                    "risk_level": "HIGH",
                    "risk_score": 0.9,
                    "explanation": "Confirmed high-risk event",
                }
            ],
            tracks=[
                {
                    "track_id": "track-1",
                    "class_name": "Person",
                    "camera_id": "cam-1",
                    "last_updated": NOW.isoformat(),
                    "risk_score": 0.9,
                    "verification_status": "confirmed",
                }
            ],
            statistics={"active_detections_count": 1, "timestamp": NOW.isoformat()},
            semantic_engine=object(),
        ),
        cameras=[
            {
                "camera_id": "cam-1",
                "name": "Camera 1",
                "runtime": {"status": "online", "last_frame_time": NOW.isoformat()},
            }
        ],
        persistence={"attempted": 1, "succeeded": 1, "last_success_at": NOW},
    )
    payload = service.build().model_dump(by_alias=True, mode="json")

    assert payload["schemaVersion"] == "1.0"
    assert "generatedAt" in payload
    assert payload["alerts"]["activeCount"] == 1
    assert payload["cameras"]["totalConfigured"] == 1
    assert IntelligenceContext.model_validate(payload).schema_version == "1.0"

    import aegis.api.routes.intelligence_context as route_module
    from aegis.api.app import APIConfig, create_app

    monkeypatch.setattr(route_module, "get_intelligence_context_service", lambda: service)
    client = TestClient(create_app(APIConfig(serve_dashboard=False)))
    unauthorized = client.get("/api/intelligence/context")
    response = client.get(
        "/api/intelligence/context", headers={"X-API-Key": os.environ["AEGIS_API_KEY"]}
    )

    assert unauthorized.status_code == 401
    assert response.status_code == 200
    assert response.json()["events"][0]["evidence"][0]["serverValidated"] is True
    assert IntelligenceContext.model_validate(response.json()).schema_version == "1.0"
