"""Focused tests for the local weapon + aggression risk layer."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np

from aegis.analysis.analysis_types import BehaviorFlags, CrowdMetrics, MotionState
from aegis.alerts.alert_manager import AlertManager, AlertManagerConfig
from aegis.risk.person_weapon_association import PersonWeaponAssociationEngine
from aegis.risk.weapon_aggression import WeaponAggressionRiskLayer
from aegis.video.camera_sources import EventSnapshot, FrameIngestionService
from config import DetectionConfig


def _track(
    track_id: int,
    class_name: str,
    bbox: tuple[int, int, int, int],
    *,
    confidence: float = 0.90,
    is_person: bool = False,
    is_weapon: bool = False,
):
    return SimpleNamespace(
        track_id=track_id,
        class_id=0 if is_person else 43 if class_name.lower() == "knife" else 34,
        class_name=class_name,
        bbox=bbox,
        confidence=confidence,
        is_person=is_person,
        is_weapon=is_weapon,
        is_vehicle=False,
        object_category="person" if is_person else "weapon" if is_weapon else "generic",
        model_source="yolo11n.pt",
    )


def _analysis(
    *,
    speed: float = 0.0,
    velocity: tuple[float, float] = (0.0, 0.0),
    acceleration: float = 0.0,
    sudden: bool = False,
):
    return SimpleNamespace(
        motion=SimpleNamespace(
            speed=speed,
            speed_smoothed=speed,
            velocity=velocity,
            acceleration=acceleration,
        ),
        behavior=SimpleNamespace(
            sudden_speed_change=sudden,
            is_erratic=False,
            is_running=False,
        ),
    )


def _capabilities() -> dict:
    return {
        "model_name": "yolo11n.pt",
        "supported_classes": ["Person", "Baseball Bat", "Knife", "Scissors"],
        "supported_weapon_classes": ["Baseball Bat", "Knife", "Scissors"],
        "weapon_detection_supported": True,
        "action_recognition_supported": False,
        "pose_estimation_supported": False,
        "semantic_verification_supported": False,
    }


def _build_evidence(track, association=None, threat_context=None):
    service = FrameIngestionService()
    service.get_model_capabilities = _capabilities
    return service._build_evidence(
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
        threat_context=threat_context,
    )


def _alert_payload(context: dict) -> dict:
    return {
        "camera_name": "North Gate",
        "track_id": "north-gate:12",
        "raw_track_id": 12,
        "risk_level": context["risk_level"],
        "risk_score": context["risk_score"],
        "risk_explanation": context["explanation"],
        "risk_factors": context["reason_codes"],
        "reason_codes": context["reason_codes"],
        "verification_status": context["verification_status"],
        "class_name": "person",
        "confidence": 0.94,
        "detected_classes": ["Person", "Knife"],
        "behavior_labels": ["normal"],
        "bbox": context["armed_person_bbox"],
        "person_track_id": context["armed_person_track_id"],
        "weapon_track_id": context["weapon_track_id"],
        "weapon_class": context["weapon_class"],
        "weapon_confidence": context["weapon_confidence"],
        "association_type": context["association_type"],
        "association_score": context["association_score"],
        "stable_frames": context["confirmed_frames"],
        "nearby_person_track_id": context["nearby_person_track_id"],
        "threat_event_type": context["event_type"],
        "threat_context": context,
        "evidence_objects": [],
    }


def test_local_model_config_enables_only_real_coco_weapon_like_classes():
    config = DetectionConfig()
    capabilities = FrameIngestionService().get_model_capabilities()

    assert {34, 43, 76}.issubset(config.target_classes)
    assert {34, 43, 76}.issubset(config.weapon_classes)
    assert config.CLASS_NAMES[43] == "Knife"
    assert config.CLASS_NAMES[34] == "Baseball Bat"
    assert config.CLASS_NAMES[76] == "Scissors"
    assert capabilities["supported_weapon_classes"] == ["Baseball Bat", "Knife", "Scissors"]
    assert capabilities["weapon_detector"]["weapon_detection_supported"] is False
    assert "gun" in capabilities["unsupported_weapon_concepts"]


def test_person_and_stable_knife_association_raise_high_risk():
    person = _track(12, "Person", (100, 100, 220, 340), is_person=True)
    knife = _track(30, "Knife", (175, 155, 195, 205), confidence=0.40, is_weapon=True)
    associations = PersonWeaponAssociationEngine()
    layer = WeaponAggressionRiskLayer()

    context = None
    association = None
    for frame_id in (1, 2):
        association = associations.assess([person, knife], frame_id=frame_id)[0]
        context = layer.assess([person, knife], [association], {}, frame_id)[0]

    evidence = _build_evidence(knife, association.to_dict(), context.to_dict())

    assert evidence["risk_level"] in {"HIGH", "CRITICAL"}
    assert evidence["verification_status"] in {"confirmed", "critical"}
    assert "POSSIBLE_ARMED_THREAT" in evidence["reason_codes"]
    assert evidence["person_track_id"] == "12"
    assert evidence["weapon_track_id"] == "30"


def test_one_strong_high_confidence_weapon_association_can_confirm_high_risk():
    person = _track(12, "Person", (100, 100, 220, 340), is_person=True)
    knife = _track(30, "Knife", (175, 155, 195, 205), confidence=0.96, is_weapon=True)
    association = PersonWeaponAssociationEngine().assess([person, knife], frame_id=1)[0]

    context = WeaponAggressionRiskLayer().assess(
        [person, knife],
        [association],
        {},
        frame_id=1,
    )[0]

    assert context.risk_level == "HIGH"
    assert context.verification_status == "confirmed"
    assert "HIGH_CONFIDENCE_WEAPON_ASSOCIATION" in context.reason_codes


def test_people_only_never_create_a_weapon_alert():
    first = _track(1, "Person", (100, 100, 200, 320), is_person=True)
    second = _track(2, "Person", (210, 100, 310, 320), is_person=True)
    layer = WeaponAggressionRiskLayer()

    context = None
    for frame_id in (1, 2, 3):
        contexts = layer.assess(
            [first, second],
            [],
            {1: _analysis(speed=18.0, velocity=(18.0, 0.0), sudden=True)},
            frame_id,
        )
        context = contexts[0]

    assert context.event_type == "possible_assault"
    assert context.risk_level == "HIGH"
    assert context.weapon_track_id is None
    assert all("WEAPON" not in code for code in context.reason_codes)
    assert "armed" not in context.explanation.lower()
    evidence = _build_evidence(first, threat_context=context.to_dict())
    assert evidence["risk_level"] == "HIGH"
    assert evidence["threat_event_type"] == "possible_assault"
    assert evidence["weapon_class"] is None


def test_weapon_far_from_person_does_not_create_armed_person_context():
    person = _track(12, "Person", (50, 50, 150, 300), is_person=True)
    knife = _track(30, "Knife", (900, 50, 930, 100), confidence=0.92, is_weapon=True)
    association = PersonWeaponAssociationEngine().assess([person, knife], frame_id=1)[0]

    contexts = WeaponAggressionRiskLayer().assess([person, knife], [association], {}, frame_id=1)
    evidence = _build_evidence(knife)

    assert association.association_type == "none"
    assert contexts == []
    assert evidence["risk_level"] == "MEDIUM"
    assert "WEAPON_DETECTED_WITHOUT_PERSON_ASSOCIATION" in evidence["reason_codes"]


def test_armed_person_second_person_closing_fast_movement_is_critical():
    association_engine = PersonWeaponAssociationEngine()
    layer = WeaponAggressionRiskLayer()
    context = None

    frames = [
        (
            _track(12, "Person", (100, 100, 200, 320), is_person=True),
            _track(30, "Knife", (165, 155, 190, 205), confidence=0.94, is_weapon=True),
            _track(18, "Person", (225, 100, 325, 320), is_person=True),
        ),
        (
            _track(12, "Person", (115, 100, 215, 320), is_person=True),
            _track(30, "Knife", (180, 155, 205, 205), confidence=0.94, is_weapon=True),
            _track(18, "Person", (225, 100, 325, 320), is_person=True),
        ),
    ]

    for frame_id, tracks in enumerate(frames, start=1):
        association = association_engine.assess(tracks, frame_id=frame_id)[0]
        contexts = layer.assess(
            tracks,
            [association],
            {12: _analysis(speed=18.0, velocity=(18.0, 0.0), sudden=True)},
            frame_id,
        )
        context = contexts[0]

    assert context.risk_level == "CRITICAL"
    assert context.nearby_person_track_id == "18"
    assert context.distance_decreasing is True
    assert context.fast_movement is True
    assert context.moving_toward_person is True
    assert "CRITICAL_WEAPON_AGGRESSION_COMBINATION" in context.reason_codes
    assert "Possible armed threat" in context.explanation
    assert "Second person track #18" in context.explanation
    assert "Fast movement toward another person" in context.explanation
    assert "Risk increased due to weapon-person association" in context.explanation
    assert "Operator review required" in context.explanation
    assert "attack confirmed" not in context.explanation.lower()


def test_upper_body_reach_region_is_recorded_without_claiming_hand_contact():
    person = _track(12, "Person", (100, 100, 200, 340), is_person=True)
    knife = _track(30, "Knife", (202, 145, 216, 180), is_weapon=True)

    association = PersonWeaponAssociationEngine().assess([person, knife], frame_id=1)[0]

    assert association.association_type == "near"
    assert association.body_region == "upper_body"
    assert "hand" not in str(association.to_dict()).lower()


def test_static_close_people_do_not_create_aggression_context():
    first = _track(1, "Person", (100, 100, 200, 320), is_person=True)
    second = _track(2, "Person", (205, 100, 305, 320), is_person=True)
    layer = WeaponAggressionRiskLayer()

    for frame_id in (1, 2, 3):
        assert layer.assess(
            [first, second],
            [],
            {1: _analysis(), 2: _analysis()},
            frame_id,
        ) == []


def test_parallel_running_people_do_not_confirm_assault():
    first = _track(1, "Person", (100, 100, 200, 320), is_person=True)
    second = _track(2, "Person", (210, 100, 310, 320), is_person=True)
    layer = WeaponAggressionRiskLayer()
    parallel_motion = _analysis(speed=18.0, velocity=(18.0, 0.0))
    parallel_motion.behavior.is_running = True

    for frame_id in (1, 2, 3):
        assert layer.assess(
            [first, second],
            [],
            {1: parallel_motion, 2: parallel_motion},
            frame_id,
        ) == []


def test_close_contact_confirmation_requires_consecutive_frames():
    first = _track(1, "Person", (100, 100, 200, 320), is_person=True)
    second = _track(2, "Person", (210, 100, 310, 320), is_person=True)
    layer = WeaponAggressionRiskLayer()
    analysis = {1: _analysis(speed=18.0, velocity=(18.0, 0.0), sudden=True)}

    contexts = [
        layer.assess([first, second], [], analysis, frame_id)[0]
        for frame_id in (1, 5, 9)
    ]

    assert [context.confirmed_frames for context in contexts] == [1, 1, 1]
    assert all(context.risk_level == "MEDIUM" for context in contexts)


def test_assault_cooldown_key_is_pair_order_independent_and_ignores_weapon_id():
    service = FrameIngestionService()
    first = {
        "threat_event_type": "possible_assault",
        "person_track_id": "12",
        "nearby_person_track_id": "18",
        "weapon_track_id": "30",
    }
    reversed_pair = {
        "threat_event_type": "possible_assault",
        "person_track_id": "18",
        "nearby_person_track_id": "12",
        "weapon_track_id": "99",
    }

    assert service._alert_confirmation_key("north-gate", first) == service._alert_confirmation_key(
        "north-gate", reversed_pair
    )


def test_composite_cooldown_prevents_duplicate_threat_alerts(monkeypatch):
    service = FrameIngestionService()
    manager = AlertManager(AlertManagerConfig(channels=set(), log_to_file=False, cooldown_seconds=60.0))
    monkeypatch.setattr(service, "_get_alert_manager", lambda: manager)
    monkeypatch.setattr(
        service,
        "_save_event_snapshot",
        lambda **_kwargs: EventSnapshot(path="data/output/snapshots/evidence.jpg", status="saved"),
    )
    persisted: list[dict] = []
    monkeypatch.setattr(service, "_persist_event", lambda event: persisted.append(event) or True)

    context = {
        "event_type": "possible_armed_threat",
        "armed_person_track_id": "12",
        "weapon_track_id": "30",
        "weapon_class": "knife",
        "weapon_confidence": 0.94,
        "nearby_person_track_id": "18",
        "risk_level": "CRITICAL",
        "risk_score": 0.90,
        "verification_status": "critical",
        "reason_codes": [
            "POSSIBLE_ARMED_THREAT",
            "CRITICAL_WEAPON_AGGRESSION_COMBINATION",
            "OPERATOR_REVIEW_REQUIRED",
        ],
        "explanation": "Possible armed threat. Operator review required.",
        "confirmed_frames": 2,
        "armed_person_bbox": [100, 100, 200, 320],
        "weapon_bbox": [165, 155, 190, 205],
        "nearby_person_bbox": [225, 100, 325, 320],
        "association_type": "contained",
        "association_score": 0.94,
    }
    payload = _alert_payload(context)
    frame = np.zeros((16, 16, 3), dtype=np.uint8)

    first = service._maybe_generate_alert("north-gate", payload, 1, datetime.now(timezone.utc), frame)
    duplicate = service._maybe_generate_alert("north-gate", payload, 2, datetime.now(timezone.utc), frame)

    assert first is not None
    assert duplicate is None
    assert len(persisted) == 1
    assert first["evidence_id"] == first["event_id"]
    assert first["related_track_ids"] == ["north-gate:30", "north-gate:18"]


def test_failed_evidence_snapshot_does_not_crash_threat_pipeline(monkeypatch):
    service = FrameIngestionService()
    manager = AlertManager(AlertManagerConfig(channels=set(), log_to_file=False))
    monkeypatch.setattr(service, "_get_alert_manager", lambda: manager)
    monkeypatch.setattr(service, "_save_event_snapshot", lambda **_kwargs: EventSnapshot(path=None, status="failed"))
    monkeypatch.setattr(service, "_persist_event", lambda _event: True)
    context = {
        "event_type": "possible_assault",
        "armed_person_track_id": "12",
        "weapon_track_id": None,
        "weapon_class": None,
        "weapon_confidence": None,
        "nearby_person_track_id": "18",
        "risk_level": "HIGH",
        "risk_score": 0.60,
        "verification_status": "confirmed",
        "reason_codes": ["POSSIBLE_ASSAULT", "CONFIRMED_AGGRESSION_PATTERN", "OPERATOR_REVIEW_REQUIRED"],
        "explanation": "Possible assault. Operator review required.",
        "confirmed_frames": 3,
        "armed_person_bbox": [100, 100, 200, 320],
        "weapon_bbox": None,
        "nearby_person_bbox": [210, 100, 310, 320],
        "association_type": None,
        "association_score": None,
    }
    payload = _alert_payload(context)
    payload["detected_classes"] = ["Person"]
    frame = np.zeros((16, 16, 3), dtype=np.uint8)

    event = service._maybe_generate_alert("north-gate", payload, 1, datetime.now(timezone.utc), frame)

    assert event is not None
    assert event["snapshot_status"] == "failed"
    assert event["snapshot_path"] is None
    assert event["title"] == "Possible assault"
    assert "attack confirmed" not in event["explanation"].lower()


def test_failed_evidence_persistence_does_not_claim_evidence_id(monkeypatch):
    service = FrameIngestionService()
    manager = AlertManager(AlertManagerConfig(channels=set(), log_to_file=False))
    monkeypatch.setattr(service, "_get_alert_manager", lambda: manager)
    monkeypatch.setattr(
        service,
        "_save_event_snapshot",
        lambda **_kwargs: EventSnapshot(path="data/output/snapshots/keyframe.jpg", status="saved"),
    )
    monkeypatch.setattr(service, "_persist_event", lambda _event: False)
    context = {
        "event_type": "possible_assault",
        "armed_person_track_id": "12",
        "weapon_track_id": None,
        "weapon_class": None,
        "weapon_confidence": None,
        "nearby_person_track_id": "18",
        "risk_level": "HIGH",
        "risk_score": 0.60,
        "verification_status": "confirmed",
        "reason_codes": ["POSSIBLE_ASSAULT", "CONFIRMED_AGGRESSION_PATTERN"],
        "explanation": "Possible assault. Operator review required.",
        "confirmed_frames": 3,
        "armed_person_bbox": [100, 100, 200, 320],
        "weapon_bbox": None,
        "nearby_person_bbox": [210, 100, 310, 320],
        "association_type": None,
        "association_score": None,
    }
    payload = _alert_payload(context)
    payload["detected_classes"] = ["Person"]

    event = service._maybe_generate_alert(
        "north-gate",
        payload,
        1,
        datetime.now(timezone.utc),
        np.zeros((16, 16, 3), dtype=np.uint8),
    )

    assert event is not None
    assert event["evidence_id"] is None
    assert event["evidence_status"] == "failed"
    assert event["incident_id"] is None


def test_alert_manager_fallback_still_deduplicates_confirmed_context(monkeypatch):
    service = FrameIngestionService()
    monkeypatch.setattr(service, "_get_alert_manager", lambda: None)
    monkeypatch.setattr(
        service,
        "_save_event_snapshot",
        lambda **_kwargs: EventSnapshot(path=None, status="failed"),
    )
    monkeypatch.setattr(service, "_persist_event", lambda _event: True)
    context = {
        "event_type": "possible_assault",
        "armed_person_track_id": "12",
        "weapon_track_id": None,
        "weapon_class": None,
        "weapon_confidence": None,
        "nearby_person_track_id": "18",
        "risk_level": "HIGH",
        "risk_score": 0.60,
        "verification_status": "confirmed",
        "reason_codes": ["POSSIBLE_ASSAULT", "CONFIRMED_AGGRESSION_PATTERN"],
        "explanation": "Possible assault. Operator review required.",
        "confirmed_frames": 3,
        "armed_person_bbox": [100, 100, 200, 320],
        "weapon_bbox": None,
        "nearby_person_bbox": [210, 100, 310, 320],
        "association_type": None,
        "association_score": None,
    }
    payload = _alert_payload(context)
    payload["detected_classes"] = ["Person"]
    frame = np.zeros((16, 16, 3), dtype=np.uint8)

    first = service._maybe_generate_alert("north-gate", payload, 1, datetime.now(timezone.utc), frame)
    duplicate = service._maybe_generate_alert("north-gate", payload, 2, datetime.now(timezone.utc), frame)

    assert first is not None
    assert duplicate is None


def test_only_actor_track_owns_a_composite_threat_event():
    context = {"armed_person_track_id": "12"}

    assert FrameIngestionService._is_primary_threat_track({
        "raw_track_id": 12,
        "person_track_id": "12",
        "threat_context": context,
    }) is True
    assert FrameIngestionService._is_primary_threat_track({
        "raw_track_id": 30,
        "person_track_id": "12",
        "threat_context": context,
    }) is False


def test_frame_ingestion_connects_tracking_context_alert_and_evidence(monkeypatch):
    service = FrameIngestionService()
    person = _track(12, "Person", (100, 100, 220, 340), is_person=True)
    knife = _track(30, "Knife", (175, 155, 195, 205), confidence=0.40, is_weapon=True)
    tracks = [knife, person]  # Weapon first verifies canonical actor ownership.
    histories = {
        track.track_id: SimpleNamespace(
            history_length=3,
            duration=0.1,
            current_position=SimpleNamespace(
                x=(track.bbox[0] + track.bbox[2]) / 2,
                y=(track.bbox[1] + track.bbox[3]) / 2,
            ),
        )
        for track in tracks
    }
    history_manager = SimpleNamespace(
        update=lambda *_args, **_kwargs: None,
        get_history=lambda track_id: histories[track_id],
    )
    motions = {track.track_id: MotionState() for track in tracks}
    behaviors = {track.track_id: BehaviorFlags() for track in tracks}
    risk_engine = SimpleNamespace(
        compute_frame_risks=lambda **_kwargs: SimpleNamespace(track_risks=[]),
    )

    monkeypatch.setattr(service, "_get_detector", lambda: SimpleNamespace(detect=lambda _frame: tracks))
    monkeypatch.setattr(service, "_get_tracker", lambda _camera_id: SimpleNamespace(update=lambda *_args: tracks))
    monkeypatch.setattr(service, "_get_history_manager", lambda _camera_id: history_manager)
    monkeypatch.setattr(service, "_get_motion_analyzer", lambda _camera_id: SimpleNamespace(analyze_all=lambda _history: motions))
    monkeypatch.setattr(service, "_get_behavior_analyzer", lambda _camera_id: SimpleNamespace(analyze_all=lambda *_args: behaviors))
    monkeypatch.setattr(service, "_get_crowd_analyzer", lambda _camera_id: SimpleNamespace(analyze=lambda *_args: CrowdMetrics(person_count=1, total_count=2)))
    monkeypatch.setattr(service, "_get_risk_engine", lambda *_args: risk_engine)
    monkeypatch.setattr(service, "_get_proximity_engine", lambda _camera_id: SimpleNamespace(assess=lambda *_args, **_kwargs: []))
    monkeypatch.setattr(
        service,
        "_apply_frame_rules",
        lambda **kwargs: (
            kwargs["base_score"],
            kwargs["base_level"],
            kwargs["base_explanation"],
            kwargs["factors"],
        ),
    )
    monkeypatch.setattr(service, "get_model_capabilities", _capabilities)
    manager = AlertManager(AlertManagerConfig(channels=set(), log_to_file=False))
    monkeypatch.setattr(service, "_get_alert_manager", lambda: manager)
    monkeypatch.setattr(
        service,
        "_save_event_snapshot",
        lambda **_kwargs: EventSnapshot(path="snapshot.jpg", status="saved"),
    )
    monkeypatch.setattr(service, "_persist_event", lambda _event: True)
    frame = np.zeros((360, 640, 3), dtype=np.uint8)

    first = service.process_frame("north-gate", frame)
    second = service.process_frame("north-gate", frame)
    alert = next(event for event in second["events"] if event.get("type") == "risk_alert")

    assert not any(event.get("type") == "risk_alert" for event in first["events"])
    assert len(second["events"]) == 1
    assert alert["track_id"] == "north-gate:12"
    assert alert["bbox"] == [100, 100, 220, 340]
    assert alert["threat_event_type"] == "possible_armed_threat"
    assert alert["evidence_id"] == alert["event_id"]
    assert {item["track_id"] for item in alert["evidence_objects"]} == {"12", "30"}
