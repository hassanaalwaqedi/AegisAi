"""Regression tests for publishing instantiated vision runtime metadata."""

from __future__ import annotations

import pytest

from datetime import datetime, timedelta

from aegis.api.state import APIState


def _runtime() -> dict:
    return {
        "backend": "ultralytics-yolo",
        "model": "yolo11n.pt",
        "configured_path": "/app/models/yolo11n.pt",
        "resolved_path": "/app/models/yolo11n.pt",
        "task": "detect",
        "class_count": 80,
        "device": "cpu",
        "ready": True,
        "error": None,
    }


def test_update_status_accepts_explicit_vision_runtime_contract():
    state = APIState()
    runtime = _runtime()

    state.update_status(
        model_name="/app/models/yolo11n.pt",
        supported_classes=["person", "car"],
        weapon_detection_supported=False,
        person_detector={"model_name": "/app/models/yolo11n.pt", "runtime": runtime},
        weapon_detector={"runtime": {"configured": True, "ready": False, "error": "missing"}},
    )

    status = state.get_status()
    assert status["model_name"] == "/app/models/yolo11n.pt"
    assert status["person_detector"]["runtime"] == runtime


def test_statistics_rejects_unknown_vision_fields():
    with pytest.raises(TypeError):
        APIState().update_statistics(model_name="yolo11n.pt")


def test_tracks_only_return_current_observations_and_keep_behavior_labels():
    state = APIState()
    state.update_track("current", behaviors=["normal", "direction_reversal"])
    state.update_track("expired", behaviors=["running"])
    state._tracks["expired"].last_updated = datetime.now() - timedelta(seconds=16)

    tracks = state.get_tracks()

    assert [track["track_id"] for track in tracks] == ["current"]
    assert tracks[0]["behaviors"] == ["normal", "direction_reversal"]
    assert tracks[0]["behavior_labels"] == ["normal", "direction_reversal"]
    assert tracks[0]["last_seen"]


@pytest.mark.asyncio
async def test_status_endpoint_reflects_instantiated_detector(monkeypatch):
    from aegis.api.routes import status as status_module

    state = APIState()
    runtime = _runtime()
    state.update_status(
        model_name="/app/models/yolo11n.pt",
        person_detector={"model_name": "/app/models/yolo11n.pt", "runtime": runtime},
        weapon_detector={"runtime": {"configured": True, "ready": False, "error": "missing"}},
    )
    monkeypatch.setattr(status_module, "get_state", lambda: state)

    payload = await status_module.get_status()

    assert payload["vision"]["status"] == "ready"
    assert payload["vision"]["general_detector"]["model"] == "yolo11n.pt"
    assert payload["vision"]["general_detector"]["class_count"] == 80


@pytest.mark.asyncio
async def test_status_reports_enabled_threat_detector_truthfully(monkeypatch):
    from aegis.api.routes import status as status_module

    state = APIState()
    state.update_status(
        person_detector={"runtime": _runtime()},
        threat_detector={
            "enabled": True,
            "runtime": {
                "backend": "ultralytics-yoloe",
                "model": "yoloe-26n-seg.pt",
                "classes": ["handgun", "knife"],
                "prompt_mode": "precomputed_text_embeddings",
                "ready": False,
                "error": "missing embeddings",
            },
        },
    )
    monkeypatch.setattr(status_module, "get_state", lambda: state)

    payload = await status_module.get_status()

    assert payload["vision"]["status"] == "degraded"
    assert payload["vision"]["threat_detector"]["model"] == "yoloe-26n-seg.pt"
    assert payload["vision"]["threat_detector"]["classes"] == ["handgun", "knife"]
