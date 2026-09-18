"""
AegisAI - Concrete Camera Source Implementations

Each class handles one source type:
- OpenCVCameraSource: local USB/device cameras
- RTSPCameraSource: RTSP network streams
- HTTPCameraSource: HTTP/HTTPS streams (including YouTube via yt-dlp)
- UploadedVideoSource: pre-recorded video files
- BrowserWebcamSource: frames pushed from a browser via WebSocket
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np

from aegis.camera.base import BaseCameraSource, OpenCVLoopCameraSource
from aegis.camera.connection_tests import CameraConnectionTestResult, endpoint_probe
from aegis.camera.types import CameraConfig, CameraConnectionStatus
from aegis.camera.utils import mask_url, validate_stream_url

logger = logging.getLogger(__name__)


class OpenCVCameraSource(OpenCVLoopCameraSource):
    """Local USB/device camera via OpenCV."""

    def __init__(self, config: CameraConfig, **kwargs):
        if config.device_index is None:
            raise ValueError("LOCAL_DEVICE requires device_index")
        super().__init__(config, capture_source=config.device_index, finite=False, **kwargs)


class RTSPCameraSource(OpenCVLoopCameraSource):
    """RTSP network camera stream."""

    def __init__(self, config: CameraConfig, **kwargs):
        validate_stream_url(config.url, {"rtsp", "rtsps"}, "RTSP_STREAM")
        super().__init__(config, capture_source=config.url, finite=False, **kwargs)


class HTTPCameraSource(OpenCVLoopCameraSource):
    """HTTP/HTTPS camera stream (includes YouTube live via yt-dlp)."""

    def __init__(self, config: CameraConfig, **kwargs):
        validate_stream_url(config.url, {"http", "https"}, "HTTP_STREAM")
        from aegis.video.youtube_resolver import is_youtube_url
        self._youtube_page_url = config.url if is_youtube_url(config.url) else None
        super().__init__(config, capture_source=config.url, finite=False, **kwargs)

    def _resolve_capture_source(self) -> str:
        if not self._youtube_page_url:
            return str(self.config.url)

        from aegis.video.youtube_resolver import resolve_youtube_stream
        resolved = resolve_youtube_stream(self._youtube_page_url)
        self.config.metadata = {
            **self.config.metadata,
            "source_resolver": "yt-dlp",
            "source_page_url": self._youtube_page_url,
            "resolved_title": resolved.title,
            "resolved_format_id": resolved.format_id,
            "resolved_height": resolved.height,
            "resolved_fps": resolved.fps,
        }
        logger.info(
            "Resolved YouTube stream for camera %s title=%s format=%s height=%s",
            self.config.camera_id,
            resolved.title,
            resolved.format_id,
            resolved.height,
        )
        return resolved.stream_url

    def _open_capture(self) -> Optional[cv2.VideoCapture]:
        if self._youtube_page_url:
            self._capture_source = self._resolve_capture_source()
        return super()._open_capture()

    def test_connection_details(self) -> CameraConnectionTestResult:
        """Return an actionable result when a YouTube page cannot resolve.

        A YouTube watch URL is deliberately supported as a source page, but
        OpenCV can only open the temporary media URL produced by yt-dlp. The
        generic connection handler used to hide that distinction as an
        unreachable camera even when youtube.com itself was reachable.
        """
        try:
            result = super().test_connection_details()
            if (
                self._youtube_page_url
                and not result.ok
                and result.error_category in {"authentication_or_stream_rejected", "no_frame"}
            ):
                return CameraConnectionTestResult(
                    ok=False,
                    status="failed",
                    error_category="youtube_media_unavailable",
                    error_message=(
                        "YouTube metadata was found, but its media stream cannot be opened for live analysis. "
                        "Use a direct RTSP, HLS, MJPEG, or MP4 stream URL, or upload a video file."
                    ),
                    dns_resolved=result.dns_resolved,
                    host_reachable=result.host_reachable,
                    masked_url=mask_url(self._youtube_page_url),
                )
            return result
        except Exception as exc:
            if not self._youtube_page_url:
                raise
            probe = endpoint_probe(self._youtube_page_url, self.config.connection_timeout)
            logger.info(
                "YouTube stream resolution failed camera_id=%s error=%s",
                self.config.camera_id,
                type(exc).__name__,
            )
            return CameraConnectionTestResult(
                ok=False,
                status="failed",
                error_category="youtube_resolution_failed",
                error_message=(
                    "YouTube was reached, but Aegis could not resolve a playable video stream. "
                    "Use a public video or live stream and ensure yt-dlp is up to date."
                ),
                dns_resolved=probe.get("dns_resolved"),
                host_reachable=probe.get("host_reachable"),
                masked_url=mask_url(self._youtube_page_url),
            )

    def _get_frame_interval(self, capture: Optional[cv2.VideoCapture]) -> Optional[float]:
        if not self._youtube_page_url:
            return None
        metadata_fps = self.config.metadata.get("resolved_fps")
        interval = self._fps_interval(float(metadata_fps)) if metadata_fps else None
        return interval or self._capture_fps_interval(capture) or self._fps_interval(30.0)



class UploadedVideoSource(OpenCVLoopCameraSource):
    """Pre-recorded video file playback."""

    def __init__(self, config: CameraConfig, **kwargs):
        if not config.upload_path or not Path(config.upload_path).exists():
            raise ValueError("UPLOADED_VIDEO requires an existing upload_path")
        super().__init__(
            config, capture_source=config.upload_path, finite=True, **kwargs
        )

    def _get_frame_interval(self, capture: Optional[cv2.VideoCapture]) -> Optional[float]:
        return self._capture_fps_interval(capture) or self._fps_interval(30.0)


class BrowserWebcamSource(BaseCameraSource):
    """Browser-pushed frames via WebSocket."""

    def start(self) -> None:
        self._running = True
        self._set_status(
            CameraConnectionStatus.CONNECTING, "Waiting for browser frames"
        )

    def stop(self) -> None:
        self._running = False
        self._set_status(CameraConnectionStatus.STOPPED, "Stopped")

    def ingest_frame(self, frame: np.ndarray, notify_pipeline: bool = True) -> None:
        if not self._running:
            self.start()
        self._publish_frame(frame, notify_pipeline=notify_pipeline)

    def test_connection(self) -> Tuple[bool, Optional[str]]:
        if self._last_frame_time is None:
            return False, "Browser webcam has not sent frames yet"
        return True, None

    def check_health(self, stale_after_seconds: float = 5.0) -> None:
        if not self._running:
            return
        if self._last_frame_time is None:
            self._set_status(
                CameraConnectionStatus.CONNECTING, "Waiting for browser frames"
            )
            return
        elapsed = (datetime.utcnow() - self._last_frame_time).total_seconds()
        if elapsed > stale_after_seconds:
            self._set_status(
                CameraConnectionStatus.RECONNECTING, "Browser frames stopped"
            )


class UnavailableCameraSource(BaseCameraSource):
    """Visible failed placeholder for a persisted source that cannot restore."""

    def __init__(self, config: CameraConfig, *, reason: str, **kwargs):
        super().__init__(config, **kwargs)
        self._set_status(CameraConnectionStatus.ERROR, reason)

    def start(self) -> None:
        # The underlying source configuration must be repaired before this
        # source can be replaced by a real factory-created implementation.
        self._set_status(CameraConnectionStatus.ERROR, self._error_message)

    def stop(self) -> None:
        self._running = False
        self._set_status(CameraConnectionStatus.STOPPED, "Stopped")

    def test_connection(self) -> Tuple[bool, Optional[str]]:
        return False, self._error_message or "Camera source is unavailable"
