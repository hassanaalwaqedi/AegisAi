"""Deterministic Phase 6 evidence-based situation assessment tests."""
from types import SimpleNamespace

from aegis.risk.situation_intelligence import SituationIntelligence


def person(track_id, box):
    return SimpleNamespace(track_id=track_id, class_name="Person", is_person=True, bbox=box)


def analysis(*, running=False, anomaly=False, loitering=False, speed=0.0):
    return SimpleNamespace(
        behavior=SimpleNamespace(is_running=running, has_anomaly=anomaly, is_erratic=anomaly, is_loitering=loitering),
        motion=SimpleNamespace(speed_smoothed=speed),
    )


def threat(track_id="27", family="handgun", *, state="probable", persistent=True, observations=4):
    return {
        "track_id": track_id, "normalized_threat_class": family, "raw_class": family,
        "detector_confidence": 0.82, "association_confidence": 0.83,
        "association_state": state, "persistence_state": "persistent" if persistent else "new",
        "observations": observations, "observed_now": True, "detector": "threat_yoloe",
    }


def by_track(items, track_id="27"):
    return next(item for item in items if item.primary_track_id == track_id)


def test_normal_and_running_are_not_automatically_high_or_critical():
    engine = SituationIntelligence()
    normal = by_track(engine.assess(camera_id="cam", tracks=[person("27", (0, 0, 80, 160))], threat_evidence=[]))
    running = by_track(engine.assess(camera_id="cam2", tracks=[person("27", (0, 0, 80, 160))], threat_evidence=[], analyses={"27": analysis(running=True, speed=25)}))
    assert normal.risk_level == "LOW"
    assert running.risk_level == "LOW"
    assert "RAPID_MOVEMENT" in running.reason_codes


def test_persistent_associated_threat_is_explainable_and_escalates_with_approach():
    engine = SituationIntelligence()
    first = [person("27", (0, 0, 80, 160)), person("31", (300, 0, 380, 160))]
    assessment = by_track(engine.assess(camera_id="cam", tracks=first, threat_evidence=[threat()], analyses={"27": analysis(speed=20)}))
    assert assessment.risk_level == "MEDIUM"
    assert {"PERSISTENT_HANDGUN_CANDIDATE", "PROBABLE_PERSON_THREAT_ASSOCIATION", "MULTI_SIGNAL_PERSISTENCE"}.issubset(assessment.reason_codes)
    second = [person("27", (170, 0, 250, 160)), person("31", (300, 0, 380, 160))]
    escalated = by_track(engine.assess(camera_id="cam", tracks=second, threat_evidence=[threat()], analyses={"27": analysis(speed=20)}))
    assert escalated.risk_level == "HIGH"
    assert "RAPID_APPROACH_TO_PERSON" in escalated.reason_codes
    assert "THREAT_APPROACH_COMBINATION" in escalated.reason_codes
    assert escalated.related_track_ids == ["31"]


def test_ambiguous_and_unassociated_threats_do_not_accuse_a_person():
    engine = SituationIntelligence()
    people = [person("27", (0, 0, 80, 160)), person("31", (150, 0, 230, 160))]
    items = engine.assess(camera_id="cam", tracks=people, threat_evidence=[threat(None, state="ambiguous")])
    assert all("PROBABLE_PERSON_THREAT_ASSOCIATION" not in item.reason_codes for item in items if item.primary_track_id)
    scene = next(item for item in items if item.primary_track_id is None)
    assert "UNASSOCIATED_HANDGUN_CANDIDATE" in scene.reason_codes


def test_risk_decays_but_peak_history_remains_after_threat_expires():
    engine = SituationIntelligence()
    tracks = [person("27", (0, 0, 80, 160))]
    raised = by_track(engine.assess(camera_id="cam", tracks=tracks, threat_evidence=[threat()]))
    current = raised
    for _ in range(4):
        current = by_track(engine.assess(camera_id="cam", tracks=tracks, threat_evidence=[]))
    assert current.risk_level == "LOW"
    assert current.peak_risk_level == "MEDIUM"
    assert current.risk_trend == "de_escalating"


def test_authorized_tool_context_moderates_but_does_not_remove_blade_evidence():
    engine = SituationIntelligence()
    zone = SimpleNamespace(zone_type=SimpleNamespace(value="NORMAL"), zone_name="authorized_tool_area")
    assessment = by_track(engine.assess(camera_id="cam", tracks=[person("27", (0, 0, 80, 160))], threat_evidence=[threat(family="blade")], zone_for_track=lambda _: zone))
    assert "AUTHORIZED_TOOL_AREA_CONTEXT" in [item.reason_code for item in assessment.contributions]
    assert "PERSISTENT_BLADE_CANDIDATE" in assessment.reason_codes


def test_temporal_state_is_removed_when_a_track_is_no_longer_active():
    engine = SituationIntelligence()
    engine.assess(camera_id="cam", tracks=[person("27", (0, 0, 80, 160))], threat_evidence=[threat()])
    assert ("cam", "27") in engine._states
    engine.assess(camera_id="cam", tracks=[], threat_evidence=[])
    assert ("cam", "27") not in engine._states
