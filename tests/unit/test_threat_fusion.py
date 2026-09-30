from types import SimpleNamespace

import numpy as np

from aegis.fusion.threat_fusion import ThreatFusionConfig, ThreatFusionEngine


def person(track_id, bbox):
    return SimpleNamespace(track_id=track_id, bbox=bbox, is_person=True, class_name="person")


def threat(label, bbox, confidence=0.8):
    return SimpleNamespace(
        bbox=bbox, class_name=label, confidence=confidence,
        evidence_type="threat_candidate", detector="threat_yoloe", model_source="yoloe-26n-seg.pt",
    )


def fuse(engine, frame, threats, people, observed=True):
    return engine.fuse("cam", frame, threats, people, threat_observed=observed)


def test_associates_inside_person_and_keeps_confidences_separate():
    item = fuse(ThreatFusionEngine(), 1, [threat("pistol", (40, 80, 60, 110), .81)], [person(7, (0, 0, 100, 220))])[0]
    assert item.track_id == "7"
    assert item.raw_class == "pistol"
    assert item.normalized_threat_class == "handgun"
    assert item.detector_confidence == .81
    assert item.association_confidence != item.detector_confidence
    assert item.association_state == "probable"


def test_expanded_person_region_associates_boundary_threat():
    item = fuse(ThreatFusionEngine(), 1, [threat("knife", (104, 75, 116, 105))], [person(7, (0, 0, 100, 200))])[0]
    assert item.track_id == "7"
    assert item.association_state == "probable"


def test_far_threat_is_unassociated_and_two_people_get_two_weapons():
    engine = ThreatFusionEngine()
    items = fuse(engine, 1, [threat("knife", (500, 500, 520, 540)), threat("rifle", (210, 60, 230, 150))], [person(1, (0, 0, 100, 220)), person(2, (180, 0, 300, 220))])
    assert any(item.association_state == "unassociated" for item in items)
    assert any(item.track_id == "2" and item.normalized_threat_class == "long_gun" for item in items)


def test_ambiguous_people_are_not_forced_to_own_threat():
    item = fuse(ThreatFusionEngine(), 1, [threat("knife", (95, 80, 105, 110))], [person(1, (0, 0, 100, 200)), person(2, (100, 0, 200, 200))])[0]
    assert item.association_state == "ambiguous"
    assert item.track_id is None


def test_synonyms_deduplicate_but_separate_handguns_do_not():
    engine = ThreatFusionEngine()
    items = fuse(engine, 1, [threat("handgun", (30, 60, 55, 100), .76), threat("pistol", (31, 61, 56, 101), .82)], [person(1, (0, 0, 120, 220))])
    assert len(items) == 1
    assert items[0].raw_class == "pistol"
    assert items[0].aliases == ["handgun", "pistol"]
    items = fuse(ThreatFusionEngine(), 1, [threat("handgun", (20, 60, 40, 90)), threat("pistol", (180, 60, 200, 90))], [person(1, (0, 0, 240, 220))])
    assert len(items) == 2


def test_temporal_retention_reappearance_and_expiry():
    engine = ThreatFusionEngine(ThreatFusionConfig(temporal_ttl_frames=3))
    first = fuse(engine, 1, [threat("knife", (40, 80, 60, 110))], [person(7, (0, 0, 100, 220))])[0]
    retained = fuse(engine, 2, [], [person(7, (0, 0, 100, 220))], observed=False)[0]
    assert retained.threat_id == first.threat_id and not retained.observed_now and retained.persistence_state == "new"
    strengthened = fuse(engine, 4, [threat("knife", (42, 80, 62, 110))], [person(7, (0, 0, 100, 220))])[0]
    assert strengthened.observations == 2 and strengthened.persistence_state == "persistent"
    assert fuse(engine, 8, [], [person(7, (0, 0, 100, 220))], observed=True) == []


def test_track_loss_becomes_stale_and_diagnostics_are_truthful():
    engine = ThreatFusionEngine(ThreatFusionConfig(temporal_ttl_frames=5))
    fuse(engine, 1, [threat("machete", (40, 80, 60, 110))], [person(7, (0, 0, 100, 220))])
    item = fuse(engine, 2, [], [], observed=False)[0]
    assert item.persistence_state == "stale"
    assert item.track_id == "7"
    assert engine.diagnostics()["active_person_tracks"] == 0


def test_tracking_stage_emits_sidecar_evidence_without_marking_threat_as_weapon(monkeypatch):
    from aegis.pipeline.tracking import TrackingStage

    stage = TrackingStage()
    active_person = person(7, (0, 0, 100, 220))
    history = SimpleNamespace(update=lambda *args, **kwargs: None, get_history=lambda *_: None)
    monkeypatch.setattr(stage, "_get_tracker", lambda _camera: SimpleNamespace(update=lambda *_: [active_person]))
    monkeypatch.setattr(stage, "_get_history_manager", lambda _camera: history)
    monkeypatch.setattr(stage, "_get_motion_analyzer", lambda _camera: SimpleNamespace(analyze_all=lambda *_: {}))
    monkeypatch.setattr(stage, "_get_behavior_analyzer", lambda _camera: SimpleNamespace(analyze_all=lambda *_: {}))
    monkeypatch.setattr(stage, "_get_crowd_analyzer", lambda _camera: SimpleNamespace(analyze=lambda *_: SimpleNamespace(density=0.0)))

    result = stage.process([{
        "camera_id": "cam", "frame_id": 1, "_frame": np.zeros((32, 32, 3), dtype=np.uint8),
        "threat_detector_executed": True,
        "detections": [
            {"bbox": [40, 80, 60, 110], "confidence": .81, "class_id": 2000, "class_name": "pistol", "object_category": "threat_candidate", "is_weapon": False, "is_person": False, "is_vehicle": False, "is_animal": False, "detector": "threat_yoloe", "evidence_type": "threat_candidate"},
        ],
    }])[0]
    evidence = result["threat_evidence"][0]
    assert evidence["track_id"] == "7"
    assert evidence["normalized_threat_class"] == "handgun"
    assert evidence["detector"] == "threat_yoloe"
