from datetime import datetime, timezone

from aegis.api.routes.cameras import _current_camera_detections


def test_current_camera_detections_uses_latest_frame_and_unique_tracks():
    detections = [
        {"track_id": "cam-1:7", "class_name": "person", "frame_id": 41},
        {"track_id": "cam-1:7", "class_name": "person", "frame_id": 42, "confidence": 0.91},
        {"track_id": "cam-1:8", "class_name": "person", "frame_id": 42, "confidence": 0.88},
        {"track_id": "cam-1:8", "class_name": "person", "frame_id": 42, "confidence": 0.89},
    ]

    current = _current_camera_detections(detections)

    assert [item["track_id"] for item in current] == ["cam-1:7", "cam-1:8"]
    assert current[1]["confidence"] == 0.89


def test_current_camera_detections_excludes_stale_observations():
    detections = [
        {
            "track_id": "cam-1:7",
            "class_name": "person",
            "frame_id": 42,
            "last_seen": "2026-09-16T19:21:03.733364",
        }
    ]

    current = _current_camera_detections(
        detections,
        now=datetime(2026, 9, 16, 19, 21, 10, tzinfo=timezone.utc),
        max_age_seconds=5,
    )

    assert current == []
