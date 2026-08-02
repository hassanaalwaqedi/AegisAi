"""
AegisAI - Base Camera Source

Abstract base class for all camera sources and the OpenCV
VideoCapture loop base class with reconnection behavior.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from datetime import datetime
from typing import Any, Deque, Optional, Tuple

import cv2
import numpy as np

from aegis.camera.types import (
    CameraConfig,
    CameraConnectionStatus,
    CameraRuntimeStatus,
    FrameCallback,
    StatusCallback,
)

logger = logging.getLogger(__name__)


class BaseCameraSource:
    """Interface for all production camera sources."""

    def __init__(
        self,
        config: CameraConfig,
        on_frame: Optional[FrameCallback] = None,
        on_status_change: Optional[StatusCallback] = None,
    ):
        self.config = config
        self.camera_id = config.camera_id
        self._on_frame = on_frame
        self._on_status_change = on_status_change
        self._status = CameraConnectionStatus.OFFLINE
        self._error_message: Optional[str] = None
        self._running = False
        self._latest_frame: Optional[np.ndarray] = None
        self._latest_jpeg: Optional[bytes] = None
        self._frame_lock = threading.RLock()
        self._frames_received = 0
        self._frames_dropped = 0
        self._reconnect_count = 0
        self._last_frame_time: Optional[datetime] = None
        self._connected_since: Optional[datetime] = None
        self._fps_samples: Deque[float] = deque(maxlen=30)
        self._last_publish_ts: Optional[float] = None
        self._width: Optional[int] = None
        self._height: Optional[int] = None

    @property
    def status(self) -> CameraConnectionStatus:
        return self._status

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def ingest_frame(self, frame: np.ndarray, notify_pipeline: bool = True) -> None:
        del notify_pipeline
        raise NotImplementedError(
            f"{self.config.source_type.value} does not accept pushed frames"
        )

    def test_connection(self) -> Tuple[bool, Optional[str]]:
        raise NotImplementedError

    def check_health(self, stale_after_seconds: float = 5.0) -> None:
        if not self._running:
            return
        if self._last_frame_time is None:
            return
        elapsed = (datetime.utcnow() - self._last_frame_time).total_seconds()
        if (
            elapsed > stale_after_seconds
            and self._status == CameraConnectionStatus.ONLINE
        ):
            self._set_status(
                CameraConnectionStatus.RECONNECTING, "No frames received recently"
            )

    def get_frame(self, timeout: float = 0.0) -> Optional[np.ndarray]:
        del timeout
        with self._frame_lock:
            return None if self._latest_frame is None else self._latest_frame.copy()

    def get_snapshot_jpeg(self) -> Optional[bytes]:
        with self._frame_lock:
            return self._latest_jpeg

    def get_status(self) -> CameraRuntimeStatus:
        fps = (
            sum(self._fps_samples) / len(self._fps_samples)
            if self._fps_samples
            else 0.0
        )
        return CameraRuntimeStatus(
            camera_id=self.camera_id,
            status=self._status,
            source_type=self.config.source_type,
            error_message=self._error_message,
            frames_received=self._frames_received,
            frames_dropped=self._frames_dropped,
            reconnect_count=self._reconnect_count,
            fps=fps,
            width=self._width,
            height=self._height,
            last_frame_time=(
                self._last_frame_time.isoformat() if self._last_frame_time else None
            ),
            connected_since=(
                self._connected_since.isoformat() if self._connected_since else None
            ),
            running=self._running,
        )

    def _set_status(
        self, status: CameraConnectionStatus, error: Optional[str] = None
    ) -> None:
        changed = status != self._status or error != self._error_message
        self._status = status
        self._error_message = error
        if status == CameraConnectionStatus.ONLINE and self._connected_since is None:
            self._connected_since = datetime.utcnow()
        if changed:
            logger.info(
                "Camera %s status=%s error=%s", self.camera_id, status.value, error
            )
            if self._on_status_change:
                self._on_status_change(self.camera_id, status, error)

    def _publish_frame(self, frame: np.ndarray, notify_pipeline: bool = True) -> None:
        now = time.time()
        if self._last_publish_ts is not None:
            delta = max(now - self._last_publish_ts, 0.001)
            self._fps_samples.append(1.0 / delta)
        self._last_publish_ts = now

        height, width = frame.shape[:2]
        encode_ok, encoded = cv2.imencode(
            ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 82]
        )
        with self._frame_lock:
            self._latest_frame = frame.copy()
            self._latest_jpeg = encoded.tobytes() if encode_ok else None
            self._width = width
            self._height = height
            self._frames_received += 1
            self._last_frame_time = datetime.utcnow()

        if self._status != CameraConnectionStatus.ONLINE:
            self._set_status(CameraConnectionStatus.ONLINE)

        if notify_pipeline and self._on_frame:
            self._on_frame(self.camera_id, frame)


class OpenCVLoopCameraSource(BaseCameraSource):
    """OpenCV VideoCapture source with reconnect behavior."""

    MAX_PLAYBACK_FPS = 30.0

    def __init__(self, *args, capture_source: Any, finite: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self._capture_source = capture_source
        self._finite = finite
        self._thread: Optional[threading.Thread] = None
        self._capture: Optional[cv2.VideoCapture] = None
        self._last_frame_publish_monotonic: Optional[float] = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._set_status(CameraConnectionStatus.CONNECTING)
        self._thread = threading.Thread(
            target=self._capture_loop, daemon=True, name=f"camera-{self.camera_id}"
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._release_capture()
        self._set_status(CameraConnectionStatus.STOPPED, "Stopped")
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def test_connection(self) -> Tuple[bool, Optional[str]]:
        capture = self._open_capture()
        try:
            if capture is None or not capture.isOpened():
                return False, "OpenCV could not open this camera source"
            ok, frame = capture.read()
            if not ok or frame is None:
                return False, "Camera opened but did not return a frame"
            return True, None
        finally:
            if capture is not None:
                capture.release()

    def _open_capture(self) -> Optional[cv2.VideoCapture]:
        if isinstance(self._capture_source, str):
            capture = cv2.VideoCapture(self._capture_source, cv2.CAP_FFMPEG)
        else:
            capture = cv2.VideoCapture(self._capture_source)

        try:
            capture.set(
                cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, self.config.connection_timeout * 1000
            )
            capture.set(
                cv2.CAP_PROP_READ_TIMEOUT_MSEC, self.config.connection_timeout * 1000
            )
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        return capture

    def _capture_loop(self) -> None:
        retry_delay = 1.0
        failures = 0
        retries = 0

        while self._running:
            self._capture = self._open_capture()
            if self._capture is None or not self._capture.isOpened():
                retries += 1
                self._reconnect_count = retries
                message = "OpenCV could not open this camera source"
                status = (
                    CameraConnectionStatus.RECONNECTING
                    if retries <= self.config.max_retries
                    else CameraConnectionStatus.ERROR
                )
                self._set_status(status, message)
                self._release_capture()
                if self.config.max_retries and retries > self.config.max_retries:
                    break
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 20.0)
                continue

            self._set_status(CameraConnectionStatus.ONLINE)
            retry_delay = 1.0
            failures = 0
            frame_interval = self._get_frame_interval(self._capture)
            self._last_frame_publish_monotonic = None

            while (
                self._running
                and self._capture is not None
                and self._capture.isOpened()
            ):
                ok, frame = self._capture.read()
                if not ok or frame is None:
                    if self._finite:
                        self._set_status(
                            CameraConnectionStatus.STOPPED,
                            "Video processing completed",
                        )
                        self._running = False
                        break
                    failures += 1
                    self._frames_dropped += 1
                    if failures >= 5:
                        self._set_status(
                            CameraConnectionStatus.RECONNECTING, "Frame reads failed"
                        )
                        self._release_capture()
                        break
                    continue

                failures = 0
                self._pace_frame(frame_interval)
                self._publish_frame(frame)

            self._release_capture()

        self._release_capture()
        if self._status not in (
            CameraConnectionStatus.ERROR,
            CameraConnectionStatus.STOPPED,
        ):
            self._set_status(CameraConnectionStatus.OFFLINE)

    def _release_capture(self) -> None:
        if self._capture is not None:
            try:
                self._capture.release()
            except Exception:
                pass
            self._capture = None

    def _get_frame_interval(
        self, capture: Optional[cv2.VideoCapture]
    ) -> Optional[float]:
        del capture
        return None

    def _fps_interval(self, fps: Optional[float]) -> Optional[float]:
        if fps is None or fps <= 0:
            return None
        return 1.0 / min(float(fps), self.MAX_PLAYBACK_FPS)

    def _capture_fps_interval(
        self, capture: Optional[cv2.VideoCapture]
    ) -> Optional[float]:
        if capture is None:
            return None
        try:
            return self._fps_interval(capture.get(cv2.CAP_PROP_FPS))
        except Exception:
            return None

    def _pace_frame(self, frame_interval: Optional[float]) -> None:
        if frame_interval is None:
            return
        now = time.monotonic()
        if self._last_frame_publish_monotonic is not None:
            elapsed = now - self._last_frame_publish_monotonic
            delay = frame_interval - elapsed
            if delay > 0:
                time.sleep(delay)
        self._last_frame_publish_monotonic = time.monotonic()
