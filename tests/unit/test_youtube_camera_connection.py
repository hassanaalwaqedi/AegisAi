"""Regression coverage for user-facing YouTube camera diagnostics."""

from aegis.camera import sources
from aegis.camera.connection_tests import CameraConnectionTestResult
from aegis.camera.sources import HTTPCameraSource
from aegis.camera.types import CameraConfig, CameraSourceType


def test_youtube_resolution_failure_is_not_reported_as_unreachable_camera(monkeypatch):
    config = CameraConfig(
        camera_id="youtube-test",
        source_type=CameraSourceType.HTTP_STREAM,
        url="https://www.youtube.com/watch?v=example",
    )
    source = HTTPCameraSource(config)

    monkeypatch.setattr(
        sources.OpenCVLoopCameraSource,
        "test_connection_details",
        lambda _self: (_ for _ in ()).throw(RuntimeError("extractor failed")),
    )
    monkeypatch.setattr(
        sources,
        "endpoint_probe",
        lambda *_args: {"dns_resolved": True, "host_reachable": True},
    )

    result = source.test_connection_details()

    assert result.ok is False
    assert result.error_category == "youtube_resolution_failed"
    assert result.host_reachable is True
    assert "playable video stream" in (result.error_message or "")


def test_youtube_media_rejection_is_not_reported_as_camera_sign_in(monkeypatch):
    config = CameraConfig(
        camera_id="youtube-media-test",
        source_type=CameraSourceType.HTTP_STREAM,
        url="https://www.youtube.com/watch?v=example",
    )
    source = HTTPCameraSource(config)
    monkeypatch.setattr(
        sources.OpenCVLoopCameraSource,
        "test_connection_details",
        lambda _self: CameraConnectionTestResult(
            ok=False,
            status="failed",
            error_category="authentication_or_stream_rejected",
            error_message="Camera rejected the stream or credentials could not be verified.",
            dns_resolved=True,
            host_reachable=True,
        ),
    )

    result = source.test_connection_details()

    assert result.error_category == "youtube_media_unavailable"
    assert "live analysis" in (result.error_message or "")
    assert "sign-in" not in (result.error_message or "").lower()
