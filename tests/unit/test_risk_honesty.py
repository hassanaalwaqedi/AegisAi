from datetime import datetime
from types import SimpleNamespace

import numpy as np

from aegis.analysis.analysis_types import BehaviorFlags, CrowdMetrics, MotionState, TrackAnalysis
from aegis.video.camera_sources import FrameIngestionService


def _person_track() -> SimpleNamespace:
    return SimpleNamespace(
        track_id=1,
        class_id=0,
        class_name="Person",
        confidence=0.93,
        bbox=(10, 10, 110, 210),
        is_person=True,
        is_weapon=False,
    )


def _analysis(motion: MotionState, behavior: BehaviorFlags, history_length: int = 12, time_tracked: float = 1.0) -> TrackAnalysis:
    return TrackAnalysis(
        track_id=1,
        class_id=0,
        class_name="Person",
        motion=motion,
        behavior=behavior,
        history_length=history_length,
        time_tracked=time_tracked,
        current_position=(60.0, 110.0),
        current_bbox=(10, 10, 110, 210),
    )


def _crowd(person_count: int = 1) -> CrowdMetrics:
    return CrowdMetrics(person_count=person_count, total_count=person_count, max_density=person_count)


def test_person_with_small_movement_stays_low_and_generates_no_event():
    service = FrameIngestionService()
    track = _person_track()
    analysis = _analysis(
        MotionState(speed=1.0, speed_smoothed=1.0, is_moving=True, distance_traveled=2.0),
        BehaviorFlags(),
    )

    score, level, explanation, factors = service._apply_frame_rules(
        track=track,
        analysis=analysis,
        base_score=0.05,
        base_level="LOW",
        base_explanation="Person detected.",
        factors=[],
        behavior_labels=["normal"],
        crowd_metrics=_crowd(),
        proximity=SimpleNamespace(triggers=[], risk_score=0.0),
    )
    evidence = service._build_evidence(
        track=track,
        bbox=track.bbox,
        risk_level=level,
        risk_score=score,
        behavior_labels=["normal"],
        raw_behavior_labels=["normal"],
        factors=factors,
        explanation=explanation,
        motion_confirmed=False,
        frame_detected_classes=["Person"],
    )

    assert evidence["risk_level"] == "LOW"
    assert evidence["verification_status"] == "confirmed"
    assert "PERSON_DETECTED" in evidence["reason_codes"]
    assert "weapon" not in evidence["explanation"].lower()

    event = service._maybe_generate_alert(
        camera_id="test-camera",
        track_payload={
            "track_id": "test-camera:1",
            "risk_level": evidence["risk_level"],
            "risk_score": evidence["risk_score"],
            "verification_status": evidence["verification_status"],
            "reason_codes": evidence["reason_codes"],
        },
        frame_number=1,
        timestamp=datetime.utcnow(),
        frame=np.zeros((8, 8, 3), dtype=np.uint8),
    )
    assert event is None


def test_fast_bbox_motion_only_is_candidate_medium_not_high_event():
    service = FrameIngestionService()
    track = _person_track()
    analysis = _analysis(
        MotionState(speed=24.0, speed_smoothed=24.0, is_moving=True, distance_traveled=140.0),
        BehaviorFlags(is_running=True),
    )

    score, level, explanation, factors = service._apply_frame_rules(
        track=track,
        analysis=analysis,
        base_score=0.6,
        base_level="HIGH",
        base_explanation="Running",
        factors=["Running"],
        behavior_labels=["running"],
        crowd_metrics=_crowd(),
        proximity=SimpleNamespace(triggers=[], risk_score=0.0),
    )
    evidence = service._build_evidence(
        track=track,
        bbox=track.bbox,
        risk_level=level,
        risk_score=score,
        behavior_labels=["running"],
        raw_behavior_labels=["running"],
        factors=factors,
        explanation=explanation,
        motion_confirmed=True,
        frame_detected_classes=["Person"],
    )

    assert evidence["risk_level"] == "CANDIDATE_MEDIUM"
    assert evidence["verification_status"] == "candidate"
    assert evidence["evidence_type"] == "temporal_behavior"
    assert evidence["risk_score"] <= 0.35

    event = service._maybe_generate_alert(
        camera_id="test-camera",
        track_payload={
            "track_id": "test-camera:1",
            "risk_level": evidence["risk_level"],
            "risk_score": evidence["risk_score"],
            "verification_status": evidence["verification_status"],
            "reason_codes": evidence["reason_codes"],
        },
        frame_number=2,
        timestamp=datetime.utcnow(),
        frame=np.zeros((8, 8, 3), dtype=np.uint8),
    )
    assert event is None


def test_unsupported_weapon_detection_reports_no_weapon_alert():
    service = FrameIngestionService()
    service.get_model_capabilities = lambda: {
        "model_name": "yolo11n.pt",
        "supported_classes": ["Person"],
        "weapon_detection_supported": False,
        "action_recognition_supported": False,
        "pose_estimation_supported": False,
        "semantic_verification_supported": False,
    }
    track = _person_track()
    evidence = service._build_evidence(
        track=track,
        bbox=track.bbox,
        risk_level="CRITICAL",
        risk_score=0.95,
        behavior_labels=["normal"],
        raw_behavior_labels=["normal"],
        factors=["weapon_overlap"],
        explanation="weapon threat",
        motion_confirmed=False,
        frame_detected_classes=["Person"],
    )

    assert evidence["risk_level"] == "LOW"
    assert evidence["verification_status"] == "unsupported"
    assert evidence["evidence_type"] == "unsupported"
    assert "WEAPON_MODEL_UNSUPPORTED" in evidence["reason_codes"]
    assert "No weapon model is currently enabled." in evidence["explanation"]


def test_weapon_model_capabilities_report_best_pt_when_configured():
    capabilities = FrameIngestionService().get_model_capabilities()

    assert capabilities["weapon_detection_supported"] is True
    assert capabilities["person_detector"]["model_name"] == "yolo11n.pt"
    assert capabilities["weapon_detector"]["supported_classes"] == ["knife", "pistol"]
    assert capabilities["action_recognition_supported"] is False
    assert capabilities["pose_estimation_supported"] is False
    assert capabilities["semantic_verification_supported"] is False


def test_event_explanation_never_mentions_weapon_when_unsupported():
    service = FrameIngestionService()
    track = _person_track()
    evidence = service._build_evidence(
        track=track,
        bbox=track.bbox,
        risk_level="HIGH",
        risk_score=0.7,
        behavior_labels=["normal"],
        raw_behavior_labels=["normal"],
        factors=["gun detected"],
        explanation="gun detected",
        motion_confirmed=False,
        frame_detected_classes=["Person"],
    )

    assert "gun detected" not in evidence["explanation"].lower()
    assert "weapon threat" not in evidence["explanation"].lower()
    assert evidence["risk_level"] == "LOW"


def test_critical_cannot_be_generated_without_critical_evidence():
    service = FrameIngestionService()
    track = _person_track()
    evidence = service._build_evidence(
        track=track,
        bbox=track.bbox,
        risk_level="CRITICAL",
        risk_score=0.9,
        behavior_labels=["running"],
        raw_behavior_labels=["running"],
        factors=["bbox_motion_candidate"],
        explanation="Motion candidate detected from bounding-box movement.",
        motion_confirmed=True,
        frame_detected_classes=["Person"],
    )

    assert evidence["risk_level"] != "CRITICAL"
    assert evidence["verification_status"] == "candidate"
