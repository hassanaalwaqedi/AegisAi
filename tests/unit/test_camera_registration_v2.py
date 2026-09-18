"""Regression coverage for the active Aegis camera registration V2 path."""

from __future__ import annotations

import asyncio
import json

import pytest

from aegis.camera.base import BaseCameraSource, OpenCVLoopCameraSource
from aegis.camera.connection_tests import (
    CameraConnectionTestResult,
    CameraConnectionTestStore,
)
from aegis.camera.credentials import DevelopmentFileCredentialStorage
from aegis.camera.manager import MultiCameraPipelineManager
from aegis.camera.registry import CameraRegistry
from aegis.camera.types import CameraConfig, CameraConnectionStatus, CameraSourceType
from aegis.camera.utils import build_rtsp_url, mask_url, normalise_stream_identity


class _FakeSource(BaseCameraSource):
    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)
        self.started = False

    def start(self):
        self.started = True
        self._running = True
        self._set_status(CameraConnectionStatus.CONNECTING)

    def stop(self):
        self._running = False
        self._set_status(CameraConnectionStatus.STOPPED, "Stopped")

    def test_connection(self):
        return True, None


class _FakeFactory:
    def __init__(self):
        self.sources: list[_FakeSource] = []

    def create(self, config, **kwargs):
        source = _FakeSource(config, **kwargs)
        self.sources.append(source)
        return source


class _Ingestion:
    def get_camera_events(self, *_args, **_kwargs):
        return []

    def get_camera_detections(self, *_args, **_kwargs):
        return []


def _manager(tmp_path, factory: _FakeFactory | None = None) -> MultiCameraPipelineManager:
    return MultiCameraPipelineManager(
        registry=CameraRegistry(tmp_path / "cameras.json"),
        factory=factory or _FakeFactory(),
        ingestion_service=_Ingestion(),
        credential_storage=DevelopmentFileCredentialStorage(tmp_path / "credentials.json"),
    )


def _rtsp_config(camera_id: str = "entrance") -> CameraConfig:
    return CameraConfig(
        camera_id=camera_id,
        source_type=CameraSourceType.RTSP_STREAM,
        url="rtsp://operator:super-secret@192.168.1.20:554/stream1?token=private-token",
    )


def _stop(manager: MultiCameraPipelineManager) -> None:
    manager.health_monitor.stop()


def test_rtsp_url_builder_and_public_masking_remove_all_credentials():
    url = build_rtsp_url(
        protocol="rtsp",
        host="192.168.1.20",
        port=554,
        stream_path="live/ch01",
        username="operator@example",
        password="p@ss word",
    )
    assert "operator%40example" in url
    assert "p%40ss%20word" in url

    public = CameraConfig(
        camera_id="masked",
        source_type=CameraSourceType.RTSP_STREAM,
        url="rtsp://operator:super-secret@192.168.1.20:554/stream1?token=private-token",
    ).to_public_dict()
    assert "operator" not in public["url"]
    assert "super-secret" not in public["url"]
    assert "private-token" not in public["url"]
    assert "operator" not in (mask_url(url) or "")


def test_active_registration_keeps_raw_rtsp_url_out_of_camera_registry(tmp_path):
    manager = _manager(tmp_path)
    try:
        payload = manager.create_camera(
            _rtsp_config(),
            auto_start=True,
            connection_verified=True,
            connection_test={"ok": True, "masked_url": "rtsp://****@192.168.1.20:554/stream1"},
        )

        registry_contents = (tmp_path / "cameras.json").read_text(encoding="utf-8")
        credentials_contents = (tmp_path / "credentials.json").read_text(encoding="utf-8")
        assert "super-secret" not in registry_contents
        assert "private-token" not in registry_contents
        assert "credential_ref" in registry_contents
        assert "super-secret" in credentials_contents  # development-only provider
        assert "super-secret" not in payload["url"]
        assert payload["registration"] == {
            "config_saved": True,
            "connection_verified": True,
            "processing_started": True,
            "runtime_status": "connecting",
            "connection_state": "connecting",
        }
    finally:
        _stop(manager)


def test_duplicate_normalised_stream_endpoint_is_rejected(tmp_path):
    manager = _manager(tmp_path)
    try:
        manager.create_camera(_rtsp_config("entrance"), connection_verified=True)
        duplicate = CameraConfig(
            camera_id="entrance-duplicate",
            source_type=CameraSourceType.RTSP_STREAM,
            url="rtsp://different-user:different-secret@192.168.1.20:554/stream1?new=token",
        )
        with pytest.raises(ValueError, match="already registered"):
            manager.create_camera(duplicate, connection_verified=True)
    finally:
        _stop(manager)


def test_youtube_stream_identity_distinguishes_videos_and_canonicalises_link_forms(tmp_path):
    first_url = "https://www.youtube.com/watch?v=HMWUygIW0o0&t=30"
    same_video_share_url = "https://youtu.be/HMWUygIW0o0"
    second_url = "https://www.youtube.com/watch?v=BAw342Xqxhs"

    assert normalise_stream_identity(first_url) == "youtube-video:HMWUygIW0o0"
    assert normalise_stream_identity(same_video_share_url) == "youtube-video:HMWUygIW0o0"
    assert normalise_stream_identity(second_url) == "youtube-video:BAw342Xqxhs"

    manager = _manager(tmp_path)
    try:
        manager.create_camera(CameraConfig("youtube-first", CameraSourceType.HTTP_STREAM, url=first_url))
        manager.create_camera(CameraConfig("youtube-second", CameraSourceType.HTTP_STREAM, url=second_url))
        with pytest.raises(ValueError, match="already registered"):
            manager.create_camera(
                CameraConfig("youtube-first-duplicate", CameraSourceType.HTTP_STREAM, url=same_video_share_url)
            )
    finally:
        _stop(manager)


def test_auto_start_is_persisted_and_restored_by_active_manager(tmp_path):
    factory = _FakeFactory()
    first = _manager(tmp_path, factory)
    try:
        first.create_camera(_rtsp_config(), auto_start=True, connection_verified=True)
    finally:
        _stop(first)

    restored_factory = _FakeFactory()
    restored = _manager(tmp_path, restored_factory)
    try:
        assert restored_factory.sources
        assert restored_factory.sources[0].started is True
        persisted = json.loads((tmp_path / "cameras.json").read_text(encoding="utf-8"))
        assert persisted["cameras"][0]["auto_start"] is True
    finally:
        _stop(restored)


def test_test_proof_is_configuration_bound_and_failed_results_are_never_online():
    store = CameraConnectionTestStore()
    config = _rtsp_config()
    failed = CameraConnectionTestResult(
        ok=False,
        status="failed",
        error_category="no_frame",
        error_message="Camera opened but returned no frame.",
    )
    failed_token = store.record(config, failed)
    assert store.verified_result(failed_token, config) is None
    assert failed.to_public_dict()["status"] == "failed"

    verified = CameraConnectionTestResult(ok=True, status="online")
    token = store.record(config, verified)
    assert store.verified_result(token, config) is verified
    changed = _rtsp_config()
    changed.url = "rtsp://operator:super-secret@192.168.1.20:554/other"
    assert store.verified_result(token, changed) is None


def test_active_rtsp_api_save_requires_a_matching_verified_test(monkeypatch: pytest.MonkeyPatch):
    from fastapi import HTTPException
    from aegis.api.routes import cameras as camera_routes

    class _RecordingManager:
        def __init__(self):
            self.received = None

        def create_camera(self, config, **kwargs):
            self.received = (config, kwargs)
            return {
                "camera_id": config.camera_id,
                "url": "rtsp://****@192.168.1.20:554/stream1",
                "registration": {
                    "config_saved": True,
                    "connection_verified": kwargs["connection_verified"],
                    "processing_started": kwargs["auto_start"],
                    "runtime_status": "connecting",
                    "connection_state": "connecting",
                },
            }

    request = camera_routes.CameraCreateRequest(
        camera_id="route-rtsp",
        source_type="RTSP_STREAM",
        rtsp_host="192.168.1.20",
        rtsp_path="stream1",
        auto_start=True,
    )
    with pytest.raises(HTTPException) as rejected:
        asyncio.run(camera_routes.create_camera(request, x_aegis_actor=None, _=True))
    assert rejected.value.status_code == 409

    result = CameraConnectionTestResult(ok=True, status="online", masked_url="rtsp://****@192.168.1.20:554/stream1")
    token = camera_routes.get_connection_test_store().record(request.to_config(), result)
    verified_request = request.model_copy(update={"connection_test_id": token})
    manager = _RecordingManager()
    monkeypatch.setattr(camera_routes, "get_camera_manager", lambda: manager)

    payload = asyncio.run(camera_routes.create_camera(verified_request, x_aegis_actor=None, _=True))
    assert manager.received is not None
    assert manager.received[1]["connection_verified"] is True
    assert payload["registration"]["config_saved"] is True
    assert payload["registration"]["runtime_status"] == "connecting"


def test_capture_open_does_not_mark_camera_online_before_a_frame_arrives():
    observed_statuses: list[CameraConnectionStatus] = []

    class _Capture:
        def isOpened(self):
            return True

        def read(self):
            observed_statuses.append(source.status)
            source._running = False
            return False, None

        def release(self):
            return None

        def set(self, *_args):
            return True

    class _Source(OpenCVLoopCameraSource):
        def _open_capture(self):
            return _Capture()

    source = _Source(
        CameraConfig(camera_id="truthful-status", source_type=CameraSourceType.LOCAL_DEVICE, device_index=0),
        capture_source=0,
    )
    source._running = True
    source._set_status(CameraConnectionStatus.CONNECTING)
    source._capture_loop()

    assert observed_statuses == [CameraConnectionStatus.CONNECTING]
    assert source.status == CameraConnectionStatus.OFFLINE
