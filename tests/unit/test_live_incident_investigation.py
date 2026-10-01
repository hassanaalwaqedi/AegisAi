from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from aegis.database.connection import Base
from aegis.database.models import Event, Incident, IncidentVerification
from aegis.database.repositories import (
    EventRepository,
    IncidentRepository,
    IncidentVerificationRepository,
    ObservationRepository,
    RiskAssessmentRepository,
)
from aegis.intelligence.context_schemas import Availability
from aegis.intelligence.incident_investigation import (
    generate_incident_report,
    get_incident,
    get_incident_evidence,
    get_incident_timeline,
    get_track_trajectory,
)
from aegis.intelligence.live_tools import LiveToolRegistry
from aegis.intelligence.live_schemas import UICommandKind


NOW = datetime.now(timezone.utc).replace(microsecond=0)
INCIDENT_ID = "incident-phase2-17"
EVENT_ID = "event-phase2-17"
SECRET_PATH = "PRIVATE_RAW_PATH_MARKER_DO_NOT_RETURN"


@pytest.fixture
def investigation_db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'investigation.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr("aegis.database.connection._SessionLocal", session_factory)
    audit_records = []
    monkeypatch.setattr("aegis.audit.record_audit", lambda action, **kwargs: audit_records.append((action, kwargs)) or True)
    with session_factory.begin() as session:
        incident = Incident(
            incident_id=INCIDENT_ID,
            camera_id="camera-test-1",
            primary_track_id="camera-test-1:17",
            related_track_ids=["camera-test-1:18"],
            zone_id="zone-north",
            zone_name="North entrance",
            start_time=NOW - timedelta(seconds=5),
            last_seen_time=NOW + timedelta(seconds=5),
            current_risk_level="HIGH",
            max_risk_score=0.72,
            status="active",
            lifecycle_status="under_review",
            lifecycle_updated_by="operator-test",
            lifecycle_updated_at=NOW + timedelta(seconds=4),
            lifecycle_reason="Operator requested review",
            event_ids=[EVENT_ID],
            evidence_ids=[EVENT_ID],
            risk_types=["POSSIBLE_ASSAULT"],
            summary_reason="Persisted interaction-risk event",
            contributing_factors=["rapid_approach", "repeated_arm_motion"],
            created_at=NOW - timedelta(seconds=5),
            updated_at=NOW + timedelta(seconds=4),
        )
        IncidentRepository(session).add(incident)
        EventRepository(session).create_or_get_evidence(
            event_id=EVENT_ID,
            incident_id=INCIDENT_ID,
            event_type="POSSIBLE_ASSAULT",
            message="Possible physical confrontation pattern.",
            reason="Two stored motion indicators were observed.",
            timestamp=NOW,
            track_key="camera-test-1:17",
            camera_id="camera-test-1",
            risk_level="HIGH",
            risk_score=0.72,
            factors=["rapid_approach", "repeated_arm_motion"],
            snapshot_path=SECRET_PATH,
            snapshot_status="saved",
            clip_path=SECRET_PATH,
            metadata={"track_ids": ["camera-test-1:17", "camera-test-1:18"]},
        )
        RiskAssessmentRepository(session).create_or_get(
            assessment_id="assessment-phase2-17",
            policy_version="risk-policy-test",
            incident_id=INCIDENT_ID,
            event_id=EVENT_ID,
            assessed_at=NOW + timedelta(seconds=2),
            risk_level="HIGH",
            policy_score=0.72,
            confidence_status="not_calibrated",
            factor_results=[{"factor": "rapid_approach", "observed": True}],
            missing_evidence=["normalized_track_history"],
            rationale="Stored risk policy rationale.",
        )
        IncidentVerificationRepository(session).create_or_get(
            verification_id="verification-phase2-17",
            incident_id=INCIDENT_ID,
            event_id=EVENT_ID,
            camera_id="camera-test-1",
            status="COMPLETED",
            combined_state="CONTRADICTED",
            provider="gemini",
            model="gemini-test",
            evidence_metadata={
                "keyframe_count": 2,
                "keyframe_timestamps": [(NOW + timedelta(seconds=1)).isoformat(), (NOW + timedelta(seconds=3)).isoformat()],
                "keyframe_frame_ids": [51, 53],
                "clip_path": SECRET_PATH,
            },
        )
        observations = ObservationRepository(session)
        for frame_id, captured_at, box, level, score in (
            (50, NOW, [10, 20, 20, 40], "MEDIUM", 0.42),
            (51, NOW + timedelta(seconds=1), [20, 20, 30, 40], "HIGH", 0.72),
        ):
            observations.create_or_get(
                observation_id=f"observation-{frame_id}",
                camera_id="camera-test-1",
                source_epoch="epoch-test",
                captured_at=captured_at,
                frame_id=frame_id,
                track_key="camera-test-1:17",
                observation_type="track_detection",
                label="person",
                model_confidence=0.91,
                bounding_box=box,
                event_id=EVENT_ID,
                metadata={"risk_level": level, "policy_score": score, "risk_factors": ["rapid_approach"]},
            )
    yield session_factory, audit_records
    engine.dispose()


def _registry():
    context = SimpleNamespace(generated_at=NOW, events=[], tracks=[])
    return LiveToolRegistry(
        session_id="phase2-session",
        operator_id="operator-test",
        correlation_id="phase2-correlation",
        context_getter=lambda: context,
    )


def test_incident_retrieval_timeline_evidence_report_and_safe_open(investigation_db):
    registry = _registry()
    incident_result = registry.execute("get_incident", {"incident_id": INCIDENT_ID})
    incident = incident_result.data
    assert incident["incident"]["severity"] == "HIGH"
    assert incident["events"][0]["factors"] == ["rapid_approach", "repeated_arm_motion"]
    assert incident["latestRiskAssessment"]["policyScore"] == 0.72
    assert incident["latestVisualLanguageVerification"]["combinedState"] == "CONTRADICTED"
    assert incident["operatorDecision"]["status"] == "under_review"
    assert incident_result.ui_command.kind == UICommandKind.OPEN_INCIDENT

    timeline = registry.execute("get_incident_timeline", {"incident_id": INCIDENT_ID}).data["items"]
    parsed = [datetime.fromisoformat(item["timestamp"]) for item in timeline]
    assert parsed == sorted(parsed)
    assert {item["kind"] for item in timeline} >= {"cv_event", "risk_assessment", "vlm_verification", "operator_decision"}

    evidence = registry.execute("get_incident_evidence", {"incident_id": INCIDENT_ID}).data
    assert evidence["snapshots"][0]["available"] is False
    assert evidence["selectedKeyframes"][0]["frameId"] == 51
    assert "PRIVATE_RAW_PATH_MARKER_DO_NOT_RETURN" not in json.dumps(evidence)
    assert "PRIVATE_RAW_PATH_MARKER_DO_NOT_RETURN" not in json.dumps(incident)
    assert "PRIVATE_RAW_PATH_MARKER_DO_NOT_RETURN" not in json.dumps(registry.execute("get_incident_verification", {"incident_id": INCIDENT_ID}).data)

    report = registry.execute("generate_incident_report", {"incident_id": INCIDENT_ID}).data
    assert report["computerVision"]["events"][0]["eventType"] == "POSSIBLE_ASSAULT"
    assert report["riskEngine"]["latest"]["rationale"] == "Stored risk policy rationale."
    assert report["visualLanguageVerification"]["combinedState"] == "CONTRADICTED"
    assert report["uncertainties"] == ["normalized_track_history"]
    assert report["references"]["eventIds"] == [EVENT_ID]

    opened = registry.execute("open_authorised_evidence", {"evidence_id": incident_result.citations[0].evidence_id})
    assert opened.ui_command.kind == UICommandKind.OPEN_INCIDENT
    assert opened.ui_command.target_id == INCIDENT_ID


def test_missing_incident_and_absent_vlm_are_truthful(investigation_db):
    registry = _registry()
    missing = registry.execute("get_incident", {"incident_id": "does-not-exist"})
    assert missing.availability == Availability.UNAVAILABLE
    assert missing.reason == "incident_not_found"
    absent = registry.execute("get_incident_verification", {"incident_id": "does-not-exist"})
    assert absent.reason == "incident_not_found"
    assert registry.execute("get_incident_verification", {"incident_id": INCIDENT_ID}).data["verification"]["verification_id"] == "verification-phase2-17"
    unavailable_track = registry.execute("get_track_trajectory", {"track_id": "404", "camera_id": "camera-test-1"})
    assert unavailable_track.availability == Availability.UNAVAILABLE
    assert "history_not_available" in unavailable_track.reason


def test_incident_without_any_vlm_record_is_explicitly_unverified(investigation_db):
    session_factory, _ = investigation_db
    with session_factory.begin() as session:
        session.query(IncidentVerification).filter(IncidentVerification.incident_id == INCIDENT_ID).delete()
    result = _registry().execute("get_incident_verification", {"incident_id": INCIDENT_ID})
    assert result.availability == Availability.LIVE
    assert result.data["verification"] is None
    assert "No visual-language verification" in result.reason


def test_persisted_track_trajectory_and_derived_pixel_speed(investigation_db):
    trajectory = get_track_trajectory("17", camera_id="camera-test-1", time_window="1h")
    assert trajectory["availability"] == "live"
    assert len(trajectory["observations"]) == 2
    assert trajectory["observations"][0]["positionPixels"] == {"x": 15.0, "y": 30.0}
    assert trajectory["observations"][1]["derivedSpeedPixelsPerSecond"] == 10.0
    assert trajectory["observations"][1]["normalizedPosition"] is None
    assert any("not calibrated physical speed" in item for item in trajectory["limitations"])


def test_available_saved_snapshot_is_metadata_only_and_opens_through_authorized_tool(investigation_db, tmp_path, monkeypatch):
    import aegis.intelligence.incident_investigation as investigation

    session_factory, _ = investigation_db
    approved_snapshot_root = tmp_path / "approved-snapshots"
    approved_snapshot_root.mkdir()
    snapshot = approved_snapshot_root / "frame-51.jpg"
    snapshot.write_bytes(b"local-test-image-bytes")
    monkeypatch.setattr(investigation, "_SNAPSHOT_ROOT", approved_snapshot_root)
    with session_factory.begin() as session:
        event = session.query(Event).filter(Event.event_id == EVENT_ID).one()
        event.snapshot_path = str(snapshot)

    evidence = get_incident_evidence(INCIDENT_ID)
    assert evidence["snapshots"][0]["available"] is True
    assert str(snapshot) not in json.dumps(evidence)
    assert "local-test-image-bytes" not in json.dumps(evidence)

    registry = _registry()
    result = registry.execute("get_incident_evidence", {"incident_id": INCIDENT_ID})
    opened = registry.execute("open_authorised_evidence", {"evidence_id": result.citations[0].evidence_id})
    assert opened.ui_command.kind == UICommandKind.SHOW_RISK_EVIDENCE
    assert opened.ui_command.target_id == EVENT_ID


def test_track_trajectory_reports_ambiguity_and_rejects_unbounded_windows(investigation_db):
    session_factory, _ = investigation_db
    with session_factory.begin() as session:
        ObservationRepository(session).create_or_get(
            observation_id="observation-other-camera",
            camera_id="camera-test-2",
            source_epoch="epoch-test-2",
            captured_at=NOW,
            frame_id=1,
            track_key="camera-test-2:17",
            observation_type="track_detection",
            label="person",
            bounding_box=[1, 1, 2, 2],
            metadata={},
        )
    ambiguous = get_track_trajectory("17")
    assert ambiguous["error"] == "ambiguous_track_id"
    with pytest.raises(ValueError, match="thirty days"):
        get_track_trajectory("17", camera_id="camera-test-1", time_window="90d")


def test_existing_gpu_usage_tool_reads_pytorch_total_memory(monkeypatch):
    import sys

    fake_cuda = SimpleNamespace(
        is_available=lambda: True,
        get_device_name=lambda _index: "Test GPU",
        memory_allocated=lambda: 512 * 1024 * 1024,
        get_device_properties=lambda _index: SimpleNamespace(total_memory=4 * 1024 * 1024 * 1024),
    )
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=fake_cuda))
    from aegis.ai.tools import get_gpu_usage

    result = get_gpu_usage()
    assert result["available"] is True
    assert result["device"] == "Test GPU"
    assert result["memory_allocated_mb"] == 512.0
    assert result["memory_total_mb"] == 4096.0


@pytest.mark.parametrize("combined_state", ["SUPPORTED", "CONTRADICTED", "UNCERTAIN", "FAILED"])
def test_report_preserves_vlm_states_as_a_secondary_source(investigation_db, combined_state):
    session_factory, _ = investigation_db
    with session_factory.begin() as session:
        verification = IncidentVerificationRepository(session).get_by_verification_id("verification-phase2-17")
        verification.combined_state = combined_state
        verification.status = "FAILED" if combined_state == "FAILED" else "COMPLETED"
        verification.verdict = "UNCERTAIN" if combined_state in {"FAILED", "UNCERTAIN"} else "NORMAL"
    report = generate_incident_report(INCIDENT_ID)
    assert report["visualLanguageVerification"]["combinedState"] == combined_state
    assert report["visualLanguageVerification"]["verdict"] in {"UNCERTAIN", "NORMAL"}
    assert report["provenance"]["visualLanguageVerification"].endswith("not ground truth")


@pytest.mark.parametrize(
    ("enabled", "camera_allowed", "expected_code"),
    [
        (False, True, "VLM_ANALYSIS_DISABLED"),
        (True, False, "VLM_ANALYSIS_NOT_AUTHORIZED_FOR_CAMERA"),
    ],
)
def test_on_demand_vlm_uses_privacy_gate_before_reading_evidence(investigation_db, monkeypatch, enabled, camera_allowed, expected_code):
    from aegis.intelligence import vlm_verifier

    class GateService:
        settings = SimpleNamespace(enabled=enabled, allows_camera=lambda _camera_id: camera_allowed)

        def _authorization_reason(self, _package):
            if not self.settings.enabled:
                return "vlm_disabled"
            return None if self.settings.allows_camera("camera-test-1") else "camera_not_allowlisted"

        @staticmethod
        def _reject_before_provider(_package, reason):
            return vlm_verifier.VLMAuthorizationError(reason)

    monkeypatch.setattr(vlm_verifier, "get_vlm_verifier", lambda: GateService())
    def unexpected_read(_path):
        raise AssertionError("privacy denial must happen before reading evidence bytes")
    monkeypatch.setattr(Path, "read_bytes", unexpected_read)

    result = _registry().execute("analyze_incident_with_vlm", {"incident_id": INCIDENT_ID})
    assert result.availability == Availability.LIVE
    assert result.data["status"] == "not_performed"
    assert result.data["code"] == expected_code


def test_multitool_incident_investigation_uses_real_stores_and_redacted_audit(investigation_db):
    registry = _registry()
    recent = registry.execute("get_recent_incidents", {"limit": 5, "since_seconds": 3600})
    assert recent.data["incidents"][0]["incidentId"] == INCIDENT_ID
    incident = registry.execute("get_incident", {"incident_id": INCIDENT_ID, "message": "sensitive operator text", "api_key": "secret-value"})
    timeline = registry.execute("get_incident_timeline", {"incident_id": incident.data["incident"]["incidentId"]})
    verification = registry.execute("get_event_verification", {"event_id": EVENT_ID})
    evidence = registry.execute("get_incident_evidence", {"incident_id": INCIDENT_ID})
    report = registry.execute("generate_incident_report", {"incident_id": INCIDENT_ID})
    filtered_events = registry.execute("get_recent_events", {"camera_id": "camera-test-1", "since_seconds": 3600})

    assert [recent.tool, incident.tool, timeline.tool, verification.tool, evidence.tool, report.tool] == [
        "get_recent_incidents", "get_incident", "get_incident_timeline", "get_event_verification", "get_incident_evidence", "generate_incident_report",
    ]
    assert verification.data["cvAssessment"]["assessmentSource"] == "computer_vision"
    assert verification.data["semanticVerification"]["combined_state"] == "CONTRADICTED"
    assert report.data["visualLanguageVerification"]["combinedState"] == "CONTRADICTED"
    assert filtered_events.data["events"][0]["eventId"] == EVENT_ID

    declarations = {tool["name"] for tool in LiveToolRegistry.declarations()}
    assert {"get_incident", "get_incident_timeline", "get_track_trajectory", "generate_incident_report", "analyze_incident_with_vlm"} <= declarations
    assert all(("query" not in record[1]["details"]["arguments"] and "message" not in record[1]["details"]["arguments"]) for record in investigation_db[1])
    assert all(record[1]["details"]["correlation_id"] == "phase2-correlation" for record in investigation_db[1])
    assert all("api_key" not in record[1]["details"]["arguments"] for record in investigation_db[1])
    assert all(record[1]["details"]["success"] for record in investigation_db[1])
