"""Regression tests for controls that protect voice responsiveness."""

import pytest

from aegis.api.routes.cameras import camera_preview_interval_seconds
from aegis.camera.manager import configured_inference_workers


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, 1), ("0", 1), ("invalid", 1), ("2", 2), ("99", 4)],
)
def test_camera_inference_workers_are_bounded(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("AEGIS_CAMERA_INFERENCE_WORKERS", raising=False)
    else:
        monkeypatch.setenv("AEGIS_CAMERA_INFERENCE_WORKERS", value)

    assert configured_inference_workers() == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, 0.2), ("0", 1.0), ("invalid", 0.2), ("10", 0.1), ("60", 1 / 15)],
)
def test_camera_preview_interval_is_bounded(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("AEGIS_CAMERA_STREAM_FPS", raising=False)
    else:
        monkeypatch.setenv("AEGIS_CAMERA_STREAM_FPS", value)

    assert camera_preview_interval_seconds() == pytest.approx(expected)
