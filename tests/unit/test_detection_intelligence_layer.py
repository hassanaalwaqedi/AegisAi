from datetime import datetime

from aegis.api.state import APIState
from aegis.video.camera_sources import FrameIngestionService


def test_api_state_registry_preserves_first_seen_and_counts_updates():
    state = APIState()
    state.update_track(
        track_id="cam-1:7",
        camera_id="cam-1",
        class_name="car",
        object_category="vehicle",
        is_vehicle=True,
        confidence=0.81,
        bbox=[10, 20, 80, 120],
        model_source=["yolo11n.pt"],
        last_seen="2026-06-24T00:00:00",
    )
    state.update_track(
        track_id="cam-1:7",
        camera_id="cam-1",
        class_name="car",
        object_category="vehicle",
        is_vehicle=True,
        confidence=0.87,
        bbox=[12, 21, 82, 121],
        model_source=["yolo11n.pt"],
        last_seen="2026-06-24T00:00:02",
    )

    registry = state.get_object_registry("cam-1")

    assert len(registry) == 1
    assert registry[0]["track_id"] == "cam-1:7"
    assert registry[0]["is_vehicle"] is True
    assert registry[0]["total_seen_count"] == 2
    assert registry[0]["confidence_history"] == [0.81, 0.87]
    assert registry[0]["duration_seconds"] == 2.0


def test_detection_event_for_low_confidence_weapon_is_candidate_not_critical(monkeypatch):
    service = FrameIngestionService()
    monkeypatch.setattr("aegis.video.camera_sources.get_state", lambda: APIState())
    timestamp = datetime.fromisoformat("2026-06-24T00:00:00")
    track_payload = {
        "track_id": "cam-1:3",
        "class_name": "knife",
        "confidence": 0.52,
        "bbox": [1, 2, 30, 40],
        "is_person": False,
        "is_vehicle": False,
        "is_weapon": True,
        "detection_model_source": "best.pt",
    }

    event = service._maybe_generate_detection_event("cam-1", track_payload, 1, timestamp)

    assert event is not None
    assert event["event_type"] == "weapon_detected"
    assert event["risk_level"] == "CANDIDATE_MEDIUM"
    assert event["verification_status"] == "candidate"
    assert "LOW_CONFIDENCE_WEAPON_CANDIDATE" in event["reason_codes"]
    assert "holding" not in event["explanation"].lower()
    assert event["model_source"] == ["best.pt"]


def test_detection_event_is_emitted_once_per_track_and_class(monkeypatch):
    service = FrameIngestionService()
    monkeypatch.setattr("aegis.video.camera_sources.get_state", lambda: APIState())
    timestamp = datetime.fromisoformat("2026-06-24T00:00:00")
    track_payload = {
        "track_id": "cam-1:9",
        "class_name": "person",
        "confidence": 0.91,
        "bbox": [1, 2, 30, 40],
        "is_person": True,
        "is_vehicle": False,
        "is_weapon": False,
        "detection_model_source": "yolo11n.pt",
    }

    first = service._maybe_generate_detection_event("cam-1", track_payload, 1, timestamp)
    second = service._maybe_generate_detection_event("cam-1", track_payload, 2, timestamp)

    assert first is not None
    assert first["event_type"] == "person_detected"
    assert first["risk_level"] == "LOW"
    assert second is None
