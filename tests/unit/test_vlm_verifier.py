"""Focused Phase 1 tests: no external Gemini request is made."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from dataclasses import replace
import time

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from aegis.ai.gemini_client import GeminiClient, GeminiConfig
from aegis.database.connection import Base
from aegis.database.repositories import EventRepository, IncidentVerificationRepository, IncidentRepository
from aegis.intelligence.live_tools import LiveToolRegistry
from aegis.intelligence.vlm_verifier import (
    EvidenceFrameBuffer,
    IncidentEvidencePackage,
    IncidentVerification,
    EvidenceFrame,
    VLMSettings,
    VLMVerificationService,
    VLMVerdict,
    VerificationStatus,
    combined_state,
)
from aegis.video.camera_sources import FrameIngestionService
import aegis.database.models  # noqa: F401


NOW = datetime(2026, 9, 30, tzinfo=timezone.utc)


def _package(*, score: float = 0.8, frames: int = 4) -> IncidentEvidencePackage:
    return IncidentEvidencePackage(
        incident_id="inc-1", camera_id="cam-1", event_id="evt-1", start_time=NOW, end_time=NOW,
        risk_score=score, risk_level="HIGH", tracks=("cam-1:17",), cv_detections=tuple(),
        behavior_signals=("rapid_approach",), risk_explanation="Rapid approach observed.",
        keyframes=tuple(),
    ) if frames == 0 else IncidentEvidencePackage(
        incident_id="inc-1", camera_id="cam-1", event_id="evt-1", start_time=NOW, end_time=NOW,
        risk_score=score, risk_level="HIGH", tracks=("cam-1:17",), cv_detections=tuple(),
        behavior_signals=("rapid_approach",), risk_explanation="Rapid approach observed.",
        keyframes=tuple(
            EvidenceFrame(timestamp=NOW, jpeg=b"jpeg", risk_score=score) for _ in range(frames)
        ),
    )


def test_gemini_image_request_uses_inline_data_and_json_schema(monkeypatch):
    client = GeminiClient(GeminiConfig(api_key="test", model="gemini-test"))
    captured = {}
    def fake_request(body):
        captured["body"] = body
        return {"candidates": [{"content": {"parts": [{"text": '{"verdict":"NORMAL"}'}]}}], "usageMetadata": {}}
    monkeypatch.setattr(client, "_make_request", fake_request)
    assert client.analyze_images("inspect", [b"image", b"second"], response_schema={"type": "object"}) == {"verdict": "NORMAL"}
    parts = captured["body"]["contents"][-1]["parts"]
    assert parts[1]["inlineData"]["mimeType"] == "image/jpeg"
    assert len(parts) == 3
    assert captured["body"]["generationConfig"]["responseMimeType"] == "application/json"


def test_bounded_keyframes_preserve_context_and_peak():
    buffer = EvidenceFrameBuffer(max_frames=8, jpeg_quality=80)
    frame = np.zeros((32, 32, 3), dtype=np.uint8)
    for score in (0.1, 0.2, 0.95, 0.3, 0.4, 0.5):
        buffer.capture("cam", frame, risk_score=score, captured_at=NOW)
    selected = buffer.select("cam", max_keyframes=4)
    assert 1 <= len(selected) <= 4
    assert any(item.risk_score == 0.95 for item in selected)


def test_event_relative_keyframes_include_pre_event_and_post_event_frames():
    buffer = EvidenceFrameBuffer(max_frames=16, jpeg_quality=80)
    frame = np.zeros((16, 16, 3), dtype=np.uint8)
    for frame_id in range(1, 11):
        buffer.capture(
            "cam", frame, risk_score=0.2, frame_id=frame_id,
            captured_at=NOW + timedelta(seconds=frame_id),
        )

    assert buffer.wait_for_post_frames("cam", event_frame_id=6, minimum_after=2, timeout_seconds=0)
    selected = buffer.select("cam", max_keyframes=6, event_frame_id=6)
    selected_ids = [item.frame_id for item in selected]
    assert len(selected) == 6
    assert any(frame_id < 6 for frame_id in selected_ids)
    assert 6 in selected_ids
    assert sum(frame_id > 6 for frame_id in selected_ids) >= 2


def test_vlm_gating_and_strict_verdict():
    service = VLMVerificationService(VLMSettings(
        enabled=True, verify_incidents=True, camera_allowlist="cam-1",
        min_risk_score=0.7, max_concurrent_requests=1,
    ))
    assert service.should_verify(_package(score=0.2))[0] is False
    assert service.should_verify(_package(frames=0))[1] == "insufficient_keyframes"
    with pytest.raises(Exception):
        IncidentVerification.model_validate({"verdict": "INVENTED", "confidence": 1, "severity": "HIGH", "summary": "x", "recommended_action": "REVIEW"})
    assert combined_state(cv_risk_level="HIGH", verdict=VLMVerdict.NORMAL).value == "CONTRADICTED"


@pytest.mark.parametrize(
    ("event_type", "verdict"),
    [
        ("POSSIBLE_ASSAULT", VLMVerdict.WEAPON_RELATED),
        ("PERSON_FALL", VLMVerdict.LIKELY_ASSAULT),
        ("WEAPON_DETECTED", VLMVerdict.PERSON_FALL),
        ("UNCLASSIFIED_CANDIDATE", VLMVerdict.OTHER_RISK),
    ],
)
def test_mismatched_risk_categories_remain_uncertain(event_type, verdict):
    assert combined_state(
        cv_risk_level="MEDIUM",
        cv_event_type=event_type,
        verdict=verdict,
    ).value == "UNCERTAIN"


def test_interrupted_processing_verifications_become_failed(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'interrupted-vlm.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session.begin() as session:
        repo = IncidentVerificationRepository(session)
        repo.create_or_get(
            verification_id="vlm-interrupted", incident_id=None, event_id="evt-interrupted",
            camera_id="cam-interrupted", status="PROCESSING", provider="gemini", model="mock",
        )
        repo.create_or_get(
            verification_id="vlm-completed", incident_id=None, event_id="evt-completed",
            camera_id="cam-interrupted", status="COMPLETED", provider="gemini", model="mock",
            combined_state="CONTRADICTED",
        )
        assert repo.fail_interrupted_processing() == 1
    with Session() as session:
        failed = IncidentVerificationRepository(session).get_by_verification_id("vlm-interrupted")
        completed = IncidentVerificationRepository(session).get_by_verification_id("vlm-completed")
        assert (failed.status, failed.combined_state) == ("FAILED", "FAILED")
        assert failed.error == "api_process_restarted_during_verification"
        assert (completed.status, completed.combined_state) == ("COMPLETED", "CONTRADICTED")
    engine.dispose()


def test_camera_allowlist_can_isolate_vlm_evidence_egress():
    settings = VLMSettings(enabled=True, camera_allowlist="authorized-boxing,authorized-staging")
    assert settings.allows_camera("authorized-boxing") is True
    assert settings.allows_camera("unapproved-live-camera") is False
    assert VLMSettings(enabled=True).allowed_camera_ids == ()
    assert VLMSettings(enabled=True).allows_camera("any-camera") is False
    assert VLMSettings(enabled=True, camera_allowlist='["cam-json"]').allows_camera("cam-json") is True


@pytest.mark.parametrize(
    ("settings", "package", "expected_reason"),
    [
        (VLMSettings(enabled=False, camera_allowlist="cam-1"), _package(), "vlm_disabled"),
        (VLMSettings(enabled=True), _package(), "camera_not_allowlisted"),
        (VLMSettings(enabled=True, camera_allowlist="another-camera"), _package(), "camera_not_allowlisted"),
    ],
)
def test_backend_authorization_gate_blocks_before_provider_client(settings, package, expected_reason, monkeypatch):
    client_factory_calls = []
    persisted = []

    def client_factory():
        client_factory_calls.append(True)
        raise AssertionError("blocked requests must not construct a provider client")

    service = VLMVerificationService(settings, client_factory=client_factory)
    monkeypatch.setattr(service, "_store_status", lambda *args, **kwargs: persisted.append((args, kwargs)))

    verification_id = service.schedule(package)

    assert verification_id.startswith("vlm-")
    assert client_factory_calls == []
    assert persisted[0][0][2] == VerificationStatus.SKIPPED
    assert persisted[0][1]["error"] == expected_reason
    assert persisted[0][1]["authorization_audit"]["camera_id"] == package.camera_id
    assert persisted[0][1]["authorization_audit"]["event_id"] == package.event_id
    assert service.metrics().get("vlm_requests_sent_total", 0) == 0
    if expected_reason == "camera_not_allowlisted":
        assert service.metrics()["vlm_requests_blocked_unauthorized_total"] == 1


def test_incident_and_candidate_verification_both_enforce_the_same_camera_gate():
    class MustNotCreateClient:
        def __call__(self):
            raise AssertionError("authorization must precede provider construction")

    for package in (_package(), _candidate_package()):
        service = VLMVerificationService(VLMSettings(enabled=True), client_factory=MustNotCreateClient())
        with pytest.raises(Exception, match="camera_not_allowlisted"):
            service.verify_now(package)
        assert service.metrics()["vlm_requests_blocked_unauthorized_total"] == 1
        assert service.metrics().get("vlm_requests_sent_total", 0) == 0


def test_camera_identity_change_cannot_bypass_deferred_authorization():
    class InlineExecutor:
        def submit(self, fn, *args):
            fn(*args)

    provider_calls = []
    status_updates = []
    service = VLMVerificationService(
        VLMSettings(enabled=True, verify_candidates=True, camera_allowlist="cam-1", max_concurrent_requests=1),
        client_factory=lambda: provider_calls.append(True),
    )
    service._executor = InlineExecutor()
    service._store_status = lambda *args, **kwargs: None
    service._update_status = lambda *args, **kwargs: status_updates.append((args, kwargs))
    original = _candidate_package()
    changed = replace(original, camera_id="cam-2")

    service.schedule_deferred(original, lambda: changed, delay_seconds=0)

    assert provider_calls == []
    assert status_updates[-1][0][1] == VerificationStatus.SKIPPED
    assert status_updates[-1][1]["error"] == "camera_not_allowlisted"
    assert service.metrics()["vlm_requests_blocked_unauthorized_total"] == 1
    assert service.metrics().get("vlm_requests_sent_total", 0) == 0


def test_unauthorized_camera_is_rejected_before_local_jpeg_encoding(monkeypatch):
    from types import SimpleNamespace
    import aegis.settings as settings_module

    monkeypatch.setattr(
        settings_module,
        "get_settings",
        lambda: SimpleNamespace(vlm=VLMSettings(enabled=True, camera_allowlist="approved-camera")),
    )
    monkeypatch.setattr(
        "aegis.intelligence.vlm_verifier.cv2.imencode",
        lambda *_args, **_kwargs: pytest.fail("unauthorized frames must be rejected before JPEG encoding"),
    )
    ingestion = FrameIngestionService()

    ingestion._capture_vlm_evidence(
        camera_id="unapproved-camera",
        frame=np.zeros((16, 16, 3), dtype=np.uint8),
        frame_id=1,
        captured_at=NOW,
        risk_score=0.8,
        track_payloads=[],
    )

    assert ingestion._vlm_evidence_buffer is None


def test_on_demand_incident_verification_checks_camera_before_reading_snapshots(monkeypatch, tmp_path):
    import aegis.intelligence.vlm_verifier as verifier_module

    snapshot = tmp_path / "must-not-be-read.jpg"
    snapshot.write_bytes(b"private-image-placeholder")
    service = VLMVerificationService(VLMSettings(enabled=True))
    incident = type("Incident", (), {
        "incident_id": "inc-private",
        "camera_id": "private-camera",
        "start_time": NOW,
        "last_seen_time": NOW,
        "max_risk_score": 0.9,
        "current_risk_level": "HIGH",
        "primary_track_id": "private-camera:1",
        "related_track_ids": [],
        "contributing_factors": [],
        "summary_reason": "test only",
    })()
    event = type("Event", (), {
        "camera_id": "private-camera",
        "event_id": "evt-private",
        "snapshot_path": str(snapshot),
        "snapshot_status": "saved",
    })()

    class IncidentRepo:
        def __init__(self, _session): pass
        def get_by_incident_id(self, _incident_id): return incident

    class EventRepo:
        def __init__(self, _session): pass
        def get_by_incident_id(self, _incident_id): return [event]

    class FakeSession:
        def __enter__(self): return self
        def __exit__(self, *_args): return False

    monkeypatch.setattr("aegis.database.connection.get_db_session", lambda: FakeSession())
    monkeypatch.setattr("aegis.database.repositories.IncidentRepository", IncidentRepo)
    monkeypatch.setattr("aegis.database.repositories.EventRepository", EventRepo)
    monkeypatch.setattr(verifier_module, "get_vlm_verifier", lambda: service)
    monkeypatch.setattr(
        "pathlib.Path.read_bytes",
        lambda *_args, **_kwargs: pytest.fail("unauthorized evidence must not be read or packaged"),
    )

    with pytest.raises(ValueError, match="camera_not_allowlisted"):
        verifier_module.build_persisted_incident_package("inc-private")
    assert service.metrics()["vlm_requests_blocked_unauthorized_total"] == 1


def test_vlm_verify_now_validates_mocked_provider_response():
    class FakeClient:
        config = type("Config", (), {"model": "gemini-mock"})()
        def verify_incident(self, *_args, **_kwargs):
            return {"verdict": "LIKELY_ASSAULT", "confidence": 0.91, "severity": "HIGH", "summary": "Visible confrontation.", "subjects": [], "observations": [], "supporting_evidence": ["contact"], "contradicting_evidence": [], "uncertainties": ["intent unknown"], "recommended_action": "REVIEW", "model": "ignored", "analysis_version": "ignored"}
    service = VLMVerificationService(VLMSettings(enabled=True, camera_allowlist="cam-1", max_concurrent_requests=1), client_factory=FakeClient)
    result = service.verify_now(_package())
    assert result.verdict == VLMVerdict.LIKELY_ASSAULT
    assert result.model == "gemini-mock"
    assert service.metrics()["vlm_requests_authorized_total"] == 1
    assert service.metrics()["vlm_requests_sent_total"] == 1


def test_vlm_provider_failure_is_isolated_from_the_caller():
    class FailingClient:
        config = type("Config", (), {"model": "gemini-mock"})()
        def verify_incident(self, *_args, **_kwargs):
            raise RuntimeError("provider unavailable")
    service = VLMVerificationService(VLMSettings(enabled=True, camera_allowlist="cam-1", max_concurrent_requests=1), client_factory=FailingClient)
    with pytest.raises(RuntimeError, match="provider unavailable"):
        service.verify_now(_package())


def test_verification_repository_stores_separate_vlm_result(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'vlm.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session.begin() as session:
        repo = IncidentVerificationRepository(session)
        record, created = repo.create_or_get(verification_id="vlm-1", incident_id="inc-1", event_id="evt-1", camera_id="cam-1", status=VerificationStatus.PENDING.value, provider="gemini", model="mock", evidence_metadata={"keyframe_count": 4})
        assert created is True
        repo.update("vlm-1", status=VerificationStatus.COMPLETED.value, verdict={"verdict": "UNCERTAIN", "confidence": 0.5, "severity": "MEDIUM", "summary": "uncertain", "subjects": [], "observations": [], "supporting_evidence": [], "contradicting_evidence": [], "uncertainties": ["blur"], "recommended_action": "REVIEW", "model": "mock", "analysis_version": "vlm-incident-v1"}, combined_state="UNCERTAIN", latency_ms=12.0)
        assert repo.latest_for_incident("inc-1").to_dict()["verdict"] == "UNCERTAIN"
    engine.dispose()


def test_live_agent_tool_retrieves_stored_verification(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'agent-vlm.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session.begin() as session:
        IncidentVerificationRepository(session).create_or_get(
            verification_id="vlm-agent", incident_id="inc-agent", event_id="evt-agent", camera_id="cam-agent",
            status="COMPLETED", provider="gemini", model="mock", evidence_metadata={"keyframe_count": 4},
        )
    import aegis.database.connection as connection
    monkeypatch.setattr(connection, "_SessionLocal", Session)
    registry = LiveToolRegistry(session_id="s", operator_id="o", correlation_id="c")
    result = registry.execute("get_incident_verification", {"incident_id": "inc-agent"})
    assert result.data["verification"]["verification_id"] == "vlm-agent"
    engine.dispose()


def _persist_candidate(session, *, event_id="evt-candidate"):
    event, created = EventRepository(session).create_or_get_evidence(
        event_id=event_id,
        event_type="POSSIBLE_ASSAULT",
        message="Possible physical confrontation pattern.",
        timestamp=NOW,
        track_id=17,
        track_key="cam-1:17",
        camera_id="cam-1",
        risk_level="MEDIUM",
        risk_score=0.42,
        factors=["rapid_approach", "repeated_arm_motion"],
        metadata={"vlm_candidate": True, "track_ids": ["cam-1:17", "cam-1:18"]},
    )
    assert created
    return event


def _persist_pending_verification(session, *, event_id="evt-candidate", verification_id="vlm-candidate"):
    return IncidentVerificationRepository(session).create_or_get(
        verification_id=verification_id,
        incident_id=None,
        event_id=event_id,
        camera_id="cam-1",
        status=VerificationStatus.PENDING.value,
        provider="gemini",
        model="gemini-test",
        evidence_metadata={"keyframe_count": 4},
    )


def _candidate_package(event_id="evt-candidate"):
    return replace(
        _package(),
        incident_id=None,
        event_id=event_id,
        risk_score=0.42,
        risk_level="MEDIUM",
        event_type="POSSIBLE_ASSAULT",
        is_candidate=True,
    )


def _install_test_database(tmp_path, monkeypatch, name):
    engine = create_engine(f"sqlite:///{tmp_path / name}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    import aegis.database.connection as connection
    monkeypatch.setattr(connection, "_SessionLocal", Session)
    return engine, Session


def test_unauthorized_verification_persists_privacy_audit_without_provider_call(tmp_path, monkeypatch):
    engine, Session = _install_test_database(tmp_path, monkeypatch, "vlm-privacy-audit.db")
    provider_calls = []
    service = VLMVerificationService(
        VLMSettings(enabled=True, verify_incidents=True),
        client_factory=lambda: provider_calls.append(True),
    )

    verification_id = service.schedule(_package())

    with Session() as session:
        record = IncidentVerificationRepository(session).get_by_verification_id(verification_id)
        assert record.status == "SKIPPED"
        audit = record.evidence_metadata["authorization"]
        assert audit["camera_id"] == "cam-1"
        assert audit["event_id"] == "evt-1"
        assert audit["authorization_decision"] == "DENY"
        assert audit["provider"] == "gemini"
        assert audit["request_allowed"] is False
        assert audit["timestamp"]
        assert record.evidence_metadata["clip_path"] is None
    assert provider_calls == []
    assert service.metrics()["vlm_requests_blocked_unauthorized_total"] == 1
    assert service.metrics().get("vlm_requests_sent_total", 0) == 0
    engine.dispose()


def test_medium_candidates_use_separate_gating_and_remain_unincidentated(tmp_path, monkeypatch):
    engine, Session = _install_test_database(tmp_path, monkeypatch, "candidate-negative.db")
    with Session.begin() as session:
        _persist_candidate(session)
        _persist_pending_verification(session)

    class NormalClient:
        config = type("Config", (), {"model": "gemini-test"})()
        def verify_incident(self, *_args, **_kwargs):
            return {
                "verdict": "NORMAL", "confidence": 0.95, "severity": "LOW",
                "summary": "The activity appears controlled.", "subjects": [], "observations": [],
                "supporting_evidence": [], "contradicting_evidence": ["controlled sparring context"],
                "uncertainties": [], "recommended_action": "NO_ACTION",
            }

    settings = VLMSettings(
        enabled=True,
        verify_candidates=True,
        camera_allowlist="cam-1",
        min_risk_score=0.70,
        candidate_min_risk_score=0.35,
        candidate_min_severity="MEDIUM",
        max_concurrent_requests=1,
    )
    service = VLMVerificationService(settings, client_factory=NormalClient)
    eligible, reason = service.should_verify(_candidate_package())
    assert eligible and reason == "eligible"
    service._process_package("vlm-candidate", _candidate_package(), time.monotonic())

    with Session() as session:
        event = EventRepository(session).get_by_event_id("evt-candidate")
        verification = IncidentVerificationRepository(session).latest_for_event("evt-candidate")
        assert event is not None and event.incident_id is None
        assert verification.combined_state == "CONTRADICTED"
        assert verification.incident_id is None
        assert IncidentRepository(session).active_count() == 0
        metrics = IncidentVerificationRepository(session).candidate_metrics()
        assert metrics["vlm_candidates_total"] == 1
        assert metrics["vlm_candidates_contradicted"] == 1
        assert metrics["vlm_false_positive_reduction_candidates"] == 1
    assert service.metrics()["vlm_candidates_contradicted"] == 1
    engine.dispose()


def test_real_detection_event_is_persisted_as_candidate_without_incident(tmp_path, monkeypatch):
    engine, Session = _install_test_database(tmp_path, monkeypatch, "candidate-event-flow.db")
    from types import SimpleNamespace
    import aegis.settings as settings_module

    monkeypatch.setattr(
        settings_module,
        "get_settings",
        lambda: SimpleNamespace(vlm=VLMSettings(
            enabled=True, verify_candidates=True, camera_allowlist="cam-1", candidate_min_risk_score=0.35,
        )),
    )
    ingestion = FrameIngestionService()
    scheduled = []
    ingestion._schedule_vlm_verification = lambda event: scheduled.append(dict(event))
    event = ingestion._maybe_generate_detection_event(
        camera_id="cam-1",
        track_payload={
            "track_id": "cam-1:17",
            "person_track_id": "cam-1:17",
            "nearby_person_track_id": "cam-1:18",
            "threat_event_type": "POSSIBLE_ASSAULT",
            "risk_level": "MEDIUM",
            "risk_score": 0.42,
            "verification_status": "candidate",
            "risk_explanation": "Ambiguous physical interaction pattern.",
            "risk_factors": ["rapid_approach", "repeated_arm_motion"],
            "class_name": "person",
            "confidence": 0.88,
        },
        frame_number=9,
        timestamp=NOW,
    )

    assert event["vlm_candidate"] is True
    assert event["evidence_status"] == "persisted"
    assert len(scheduled) == 1
    with Session() as session:
        persisted = EventRepository(session).get_by_event_id(event["event_id"])
        assert persisted is not None
        assert persisted.event_type == "POSSIBLE_ASSAULT"
        assert persisted.risk_level == "MEDIUM" and persisted.risk_score == pytest.approx(0.42)
        assert persisted.incident_id is None
        assert persisted.event_metadata["vlm_candidate"] is True
        assert "cam-1:18" in persisted.event_metadata["track_ids"]
        assert IncidentRepository(session).active_count() == 0
    engine.dispose()


def test_supported_candidate_does_not_promote_without_cv_correlation(tmp_path, monkeypatch):
    engine, Session = _install_test_database(tmp_path, monkeypatch, "candidate-positive.db")
    with Session.begin() as session:
        _persist_candidate(session)
        _persist_pending_verification(session)

    class SupportingClient:
        config = type("Config", (), {"model": "gemini-test"})()
        def verify_incident(self, *_args, **_kwargs):
            return {
                "verdict": "LIKELY_ASSAULT", "confidence": 0.91, "severity": "HIGH",
                "summary": "The supplied frames show a likely physical confrontation.",
                "subjects": [], "observations": [], "supporting_evidence": ["repeated physical contact"],
                "contradicting_evidence": [], "uncertainties": ["intent is not inferred"],
                "recommended_action": "REVIEW",
            }

    settings = VLMSettings(enabled=True, camera_allowlist="cam-1", max_concurrent_requests=1)
    service = VLMVerificationService(settings, client_factory=SupportingClient)
    service._process_package("vlm-candidate", _candidate_package(), time.monotonic())

    with Session() as session:
        event = EventRepository(session).get_by_event_id("evt-candidate")
        verification = IncidentVerificationRepository(session).latest_for_event("evt-candidate")
        assert event is not None and event.incident_id is None
        assert verification.combined_state == "SUPPORTED"
        assert verification.incident_id is None
        assert IncidentRepository(session).active_count() == 0
        assert IncidentVerificationRepository(session).candidate_metrics()["vlm_candidates_supported"] == 1
    assert service.metrics()["vlm_candidates_supported"] == 1
    engine.dispose()


def test_live_agent_explains_event_level_cv_and_vlm_assessments(tmp_path, monkeypatch):
    engine, Session = _install_test_database(tmp_path, monkeypatch, "candidate-agent.db")
    with Session.begin() as session:
        _persist_candidate(session)
        _persist_pending_verification(session)
        IncidentVerificationRepository(session).update(
            "vlm-candidate",
            status="COMPLETED",
            verdict={
                "verdict": "NORMAL", "confidence": 0.95, "severity": "LOW",
                "summary": "Controlled activity visible.", "subjects": [], "observations": [],
                "supporting_evidence": [], "contradicting_evidence": ["controlled context"],
                "uncertainties": [], "recommended_action": "NO_ACTION",
            },
            combined_state="CONTRADICTED",
        )

    registry = LiveToolRegistry(session_id="s", operator_id="o", correlation_id="c")
    result = registry.execute("get_event_verification", {"event_id": "evt-candidate"})
    assert result.data["cvAssessment"]["assessmentSource"] == "computer_vision"
    assert result.data["semanticVerification"]["combined_state"] == "CONTRADICTED"
    assert "no incident was promoted" in result.data["escalationExplanation"]
    engine.dispose()


def test_candidate_provider_failure_records_failed_without_erasing_event(tmp_path, monkeypatch):
    engine, Session = _install_test_database(tmp_path, monkeypatch, "candidate-failure.db")
    with Session.begin() as session:
        _persist_candidate(session)
        _persist_pending_verification(session)
    service = VLMVerificationService(VLMSettings(enabled=True, camera_allowlist="cam-1", max_concurrent_requests=1))
    service._record_failure("vlm-candidate", _candidate_package(), time.monotonic(), RuntimeError("provider unavailable"))

    with Session() as session:
        event = EventRepository(session).get_by_event_id("evt-candidate")
        verification = IncidentVerificationRepository(session).latest_for_event("evt-candidate")
        assert event is not None and event.incident_id is None
        assert verification.status == "FAILED"
        assert verification.combined_state == "FAILED"
        assert IncidentVerificationRepository(session).candidate_metrics()["vlm_candidate_failures"] == 1
    assert service.metrics()["vlm_candidate_failures"] == 1
    engine.dispose()


@pytest.mark.parametrize(
    ("event_frame_id", "frame_ids"),
    [(4, (1, 2, 3, 4)), (1, (1, 2, 3, 4))],
)
def test_candidate_without_pre_or_post_event_frames_is_not_sent_to_gemini(
    tmp_path, monkeypatch, event_frame_id, frame_ids
):
    engine, Session = _install_test_database(tmp_path, monkeypatch, "candidate-no-post-frames.db")
    with Session.begin() as session:
        _persist_candidate(session)
        _persist_pending_verification(session)

    class MustNotCallClient:
        config = type("Config", (), {"model": "gemini-test"})()
        def verify_incident(self, *_args, **_kwargs):
            raise AssertionError("insufficient post-event evidence must not be sent")

    package = replace(
        _candidate_package(),
        event_frame_id=event_frame_id,
        keyframes=tuple(
            EvidenceFrame(timestamp=NOW, jpeg=b"jpeg", risk_score=0.42, frame_id=frame_id)
            for frame_id in frame_ids
        ),
    )
    service = VLMVerificationService(
        VLMSettings(enabled=True, verify_candidates=True, camera_allowlist="cam-1", max_concurrent_requests=1),
        client_factory=MustNotCallClient,
    )
    assert service._slots.acquire(blocking=False)
    service._run_deferred("vlm-candidate", package, lambda: package, 0.0)

    with Session() as session:
        verification = IncidentVerificationRepository(session).latest_for_event("evt-candidate")
        assert verification.status == "SKIPPED"
        assert verification.combined_state == "INSUFFICIENT_EVIDENCE"
        assert verification.error == "insufficient_pre_or_post_event_keyframes"
        assert EventRepository(session).get_by_event_id("evt-candidate").incident_id is None
    engine.dispose()
