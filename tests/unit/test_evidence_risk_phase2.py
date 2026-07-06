from types import SimpleNamespace

from aegis.explain import EvidenceExplainer
from aegis.risk.person_weapon_association import PersonWeaponAssociationEngine
from aegis.video.camera_sources import FrameIngestionService


def _track(track_id, class_name, bbox, confidence=0.9, is_person=False, is_weapon=False, is_vehicle=False):
    return SimpleNamespace(
        track_id=track_id,
        class_id=0 if is_person else (1000 if class_name == "knife" else 1001 if class_name == "pistol" else 2),
        class_name=class_name,
        bbox=bbox,
        confidence=confidence,
        is_person=is_person,
        is_weapon=is_weapon,
        is_vehicle=is_vehicle,
        object_category="weapon" if is_weapon else ("vehicle" if is_vehicle else "person" if is_person else "generic"),
        model_source="best.pt" if is_weapon else "yolo11n.pt",
    )


def _service():
    service = FrameIngestionService()
    service.get_model_capabilities = lambda: {
        "model_name": "yolo11n.pt",
        "supported_classes": ["person", "car", "knife", "pistol"],
        "weapon_detection_supported": True,
        "action_recognition_supported": False,
        "pose_estimation_supported": False,
        "semantic_verification_supported": False,
    }
    return service


def _evidence_for(track, association=None):
    return _service()._build_evidence(
        track=track,
        bbox=track.bbox,
        risk_level="LOW",
        risk_score=0.0,
        behavior_labels=["normal"],
        raw_behavior_labels=["normal"],
        factors=[],
        explanation=f"{track.class_name} detected",
        motion_confirmed=False,
        frame_detected_classes=[track.class_name],
        association=association,
    )


def test_person_only_is_low_with_no_event_level_language():
    evidence = _evidence_for(_track(1, "person", (10, 10, 110, 220), is_person=True))

    assert evidence["risk_level"] == "LOW"
    assert evidence["verification_status"] == "confirmed"
    assert "PERSON_DETECTED" in evidence["reason_codes"]
    assert "weapon" not in evidence["explanation"].lower()


def test_knife_only_is_medium_candidate():
    evidence = _evidence_for(_track(2, "knife", (200, 40, 230, 80), confidence=0.82, is_weapon=True))

    assert evidence["risk_level"] == "MEDIUM"
    assert evidence["verification_status"] == "candidate"
    assert evidence["association_type"] is None
    assert "without person association" in evidence["explanation"].lower()


def test_low_confidence_pistol_needs_verification():
    evidence = _evidence_for(_track(3, "pistol", (200, 40, 230, 80), confidence=0.31, is_weapon=True))

    assert evidence["risk_level"] == "CANDIDATE_MEDIUM"
    assert evidence["verification_status"] == "needs_verification"
    assert "below verification threshold" in evidence["explanation"].lower()


def test_knife_near_person_becomes_high_after_temporal_confirmation():
    person = _track(10, "person", (100, 100, 220, 340), is_person=True)
    knife = _track(11, "knife", (235, 170, 260, 205), confidence=0.91, is_weapon=True)
    engine = PersonWeaponAssociationEngine()

    association = None
    for frame_id in range(2):
        association = engine.assess([person, knife], frame_id=frame_id)[0].to_dict()

    evidence = _evidence_for(knife, association=association)

    assert association["association_type"] == "near"
    assert association["stable_frames"] == 2
    assert evidence["risk_level"] == "HIGH"
    assert evidence["verification_status"] == "confirmed"
    assert "WEAPON_NEAR_PERSON_STABLE" in evidence["reason_codes"]


def test_stable_contained_weapon_association_becomes_critical():
    person = _track(20, "person", (100, 100, 260, 360), is_person=True)
    knife = _track(21, "knife", (150, 170, 180, 220), confidence=0.95, is_weapon=True)
    engine = PersonWeaponAssociationEngine()

    association = None
    for frame_id in range(3):
        association = engine.assess([person, knife], frame_id=frame_id)[0].to_dict()

    evidence = _evidence_for(knife, association=association)

    assert association["association_type"] == "contained"
    assert association["stable_frames"] == 3
    assert evidence["risk_level"] == "CRITICAL"
    assert evidence["verification_status"] == "critical"
    assert "STABLE_WEAPON_PERSON_ASSOCIATION" in evidence["reason_codes"]
    assert "holding" not in evidence["explanation"].lower()


def test_single_frame_contained_weapon_is_not_critical():
    person = _track(30, "person", (100, 100, 260, 360), is_person=True)
    pistol = _track(31, "pistol", (150, 170, 180, 220), confidence=0.96, is_weapon=True)
    association = PersonWeaponAssociationEngine().assess([person, pistol], frame_id=1)[0].to_dict()

    evidence = _evidence_for(pistol, association=association)

    assert association["association_type"] == "contained"
    assert association["stable_frames"] == 1
    assert evidence["risk_level"] == "MEDIUM"
    assert evidence["verification_status"] == "candidate"
    assert "CRITICAL" not in evidence["reason_codes"]


def test_explainer_does_not_invent_behavior_language():
    text = EvidenceExplainer().explain_track(
        class_name="knife",
        confidence=0.95,
        is_weapon=True,
        association={
            "person_track_id": "17",
            "association_type": "contained",
            "stable_frames": 5,
            "association_score": 0.88,
        },
        verification_status="critical",
        risk_level="CRITICAL",
    ).lower()

    for forbidden in ("fight", "fall", "running", "holding", "attack"):
        assert forbidden not in text
