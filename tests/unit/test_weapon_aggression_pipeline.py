"""Integration checks for the stream-based weapon/aggression path."""

from types import SimpleNamespace

import numpy as np

from aegis.pipeline.alerting import AlertingStage
from aegis.pipeline.risk_scoring import RiskScoringStage


def _track(track_id, class_name, bbox, *, is_person=False, is_weapon=False, confidence=0.9):
    return SimpleNamespace(
        track_id=track_id,
        class_id=0 if is_person else 43,
        class_name=class_name,
        bbox=bbox,
        confidence=confidence,
        is_person=is_person,
        is_weapon=is_weapon,
        is_vehicle=False,
        is_animal=False,
        object_category="person" if is_person else "weapon",
        model_source="yolo11n.pt",
    )


def test_risk_scoring_stage_emits_confirmed_weapon_context_after_two_frames(monkeypatch):
    stage = RiskScoringStage()
    monkeypatch.setattr(stage, "_get_risk_engine", lambda _camera_id: None)
    monkeypatch.setattr(stage, "_get_proximity_engine", lambda _camera_id: None)
    person = _track(12, "Person", (100, 100, 220, 340), is_person=True)
    knife = _track(30, "Knife", (175, 155, 195, 205), is_weapon=True, confidence=0.40)

    first = stage.process([{
        "camera_id": "north-gate",
        "frame_id": 1,
        "timestamp": 1.0,
        "track_count": 2,
        "_tracks": [person, knife],
        "_track_analyses_raw": {},
    }])[0]
    second = stage.process([{
        "camera_id": "north-gate",
        "frame_id": 2,
        "timestamp": 2.0,
        "track_count": 2,
        "_tracks": [person, knife],
        "_track_analyses_raw": {},
    }])[0]

    assert first["risks"][0]["level"] == "MEDIUM"
    risk = second["risks"][0]
    assert risk["track_id"] == "12"
    assert risk["level"] == "HIGH"
    assert risk["event_type"] == "possible_armed_threat"
    assert risk["weapon_track_id"] == "30"
    assert risk["bbox"] == [100.0, 100.0, 220.0, 340.0]
    assert any(item["bbox"] == [175.0, 155.0, 195.0, 205.0] for item in risk["evidence_objects"])


def test_risk_scoring_stage_marks_unassociated_weapon_for_medium_review(monkeypatch):
    stage = RiskScoringStage()
    monkeypatch.setattr(stage, "_get_risk_engine", lambda _camera_id: None)
    monkeypatch.setattr(stage, "_get_proximity_engine", lambda _camera_id: None)
    knife = _track(30, "Knife", (500, 50, 530, 100), is_weapon=True, confidence=0.90)

    result = stage.process([{
        "camera_id": "north-gate",
        "frame_id": 1,
        "timestamp": 1.0,
        "track_count": 1,
        "_tracks": [knife],
        "_track_analyses_raw": {},
    }])[0]

    assert result["risks"][0]["level"] == "MEDIUM"
    assert result["risks"][0]["event_type"] == "weapon_detected"
    assert "WEAPON_DETECTED_WITHOUT_PERSON_ASSOCIATION" in result["risks"][0]["reason_codes"]


def test_alerting_stage_persists_one_composite_threat_event(monkeypatch):
    stage = AlertingStage()
    monkeypatch.setattr(stage, "_save_snapshot", lambda **_kwargs: ("snapshot.jpg", "saved"))

    persisted = []

    def persist(event):
        persisted.append(dict(event))
        event["incident_id"] = "inc-1"
        return True

    monkeypatch.setattr(stage, "_persist_event", persist)
    monkeypatch.setattr(stage, "_trigger_alert", lambda _event: None)
    risk = {
        "track_id": "12",
        "person_track_id": "12",
        "weapon_track_id": "30",
        "nearby_person_track_id": "18",
        "score": 0.90,
        "level": "CRITICAL",
        "is_concerning": True,
        "event_type": "possible_armed_threat",
        "explanation": "Possible armed threat. Operator review required.",
        "reason_codes": ["CRITICAL_WEAPON_AGGRESSION_COMBINATION"],
        "bbox": [100, 100, 200, 320],
        "evidence_objects": [
            {"object_class": "knife", "track_id": "30", "bbox": [165, 155, 190, 205]},
        ],
        "threat_context": {"confirmed_frames": 2},
    }
    message = {
        "camera_id": "north-gate",
        "frame_id": 2,
        "timestamp": 2.0,
        "track_count": 3,
        "risks": [risk],
        "max_risk_score": 0.90,
        "concerning_count": 1,
        "_frame": np.zeros((10, 10, 3), dtype=np.uint8),
    }

    first = stage.process([message])
    duplicate = stage.process([{**message, "frame_id": 3, "timestamp": 3.0}])

    assert len(first) == 1
    assert duplicate == []
    assert len(persisted) == 1
    assert first[0]["evidence_id"] == first[0]["event_id"]
    assert first[0]["incident_id"] == "inc-1"
    assert first[0]["related_track_ids"] == ["north-gate:30", "north-gate:18"]
