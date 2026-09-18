from __future__ import annotations

from aegis.camera import CameraConfig, CameraSourceType
from aegis.camera import CameraConnectionStatus
from aegis.camera.base import OpenCVLoopCameraSource
import aegis.camera.base as camera_base


class _Capture:
    def set(self, *_args):
        return True


def test_windows_local_camera_uses_directshow(monkeypatch):
    calls = []
    monkeypatch.setattr(camera_base.sys, "platform", "win32")
    monkeypatch.setattr(camera_base.cv2, "VideoCapture", lambda *args: calls.append(args) or _Capture())

    source = OpenCVLoopCameraSource(
        CameraConfig(
            camera_id="local-device",
            source_type=CameraSourceType.LOCAL_DEVICE,
            device_index=0,
        ),
        capture_source=0,
    )

    source._open_capture()

    assert calls == [(0, camera_base.cv2.CAP_DSHOW)]


def test_late_capture_open_does_not_revive_a_stopped_camera():
    class _LateCapture(_Capture):
        def isOpened(self):
            return False

        def release(self):
            return None

    class _Source(OpenCVLoopCameraSource):
        def _open_capture(self):
            self._running = False
            self._set_status(CameraConnectionStatus.STOPPED, "Stopped")
            return _LateCapture()

    source = _Source(
        CameraConfig(
            camera_id="late-network-source",
            source_type=CameraSourceType.RTSP_STREAM,
            url="rtsp://camera.example/live",
        ),
        capture_source="rtsp://camera.example/live",
    )
    source._running = True

    source._capture_loop()

    assert source.get_status().status == CameraConnectionStatus.STOPPED
    assert source.get_status().reconnect_count == 0


def test_release_during_read_is_a_clean_shutdown():
    class _InterruptedCapture(_Capture):
        def isOpened(self):
            return True

        def read(self):
            source._running = False
            source._set_status(CameraConnectionStatus.STOPPED, "Stopped")
            raise camera_base.cv2.error("capture released")

        def release(self):
            return None

    class _Source(OpenCVLoopCameraSource):
        def _open_capture(self):
            return _InterruptedCapture()

    source = _Source(
        CameraConfig(
            camera_id="interrupted-network-source",
            source_type=CameraSourceType.RTSP_STREAM,
            url="rtsp://camera.example/live",
        ),
        capture_source="rtsp://camera.example/live",
    )
    source._running = True

    source._capture_loop()

    assert source.get_status().status == CameraConnectionStatus.STOPPED
