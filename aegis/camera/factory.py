"""
AegisAI - Camera Source Factory

Creates the appropriate camera source based on CameraSourceType.
"""

from __future__ import annotations

from typing import Optional, Tuple

from aegis.camera.connection_tests import CameraConnectionTestResult
from aegis.camera.types import CameraConfig, CameraSourceType, FrameCallback, StatusCallback
from aegis.camera.base import BaseCameraSource
from aegis.camera.sources import (
    OpenCVCameraSource,
    RTSPCameraSource,
    HTTPCameraSource,
    BrowserWebcamSource,
    UploadedVideoSource,
)


class CameraSourceFactory:
    """Creates camera source instances based on configuration."""

    def create(
        self,
        config: CameraConfig,
        on_frame: Optional[FrameCallback] = None,
        on_status_change: Optional[StatusCallback] = None,
    ) -> BaseCameraSource:
        """Create a camera source for the given configuration."""
        kwargs = {"on_frame": on_frame, "on_status_change": on_status_change}
        if config.source_type == CameraSourceType.LOCAL_DEVICE:
            return OpenCVCameraSource(config, **kwargs)
        if config.source_type == CameraSourceType.RTSP_STREAM:
            return RTSPCameraSource(config, **kwargs)
        if config.source_type == CameraSourceType.HTTP_STREAM:
            # Route YouTube URLs through the dedicated YouTube pipeline
            # (yt-dlp → ffmpeg subprocess) instead of plain OpenCV.
            from aegis.video.youtube_resolver import is_youtube_url
            if is_youtube_url(config.url):
                from aegis.camera.youtube_source import YouTubeCameraSource
                return YouTubeCameraSource(config, **kwargs)
            return HTTPCameraSource(config, **kwargs)
        if config.source_type == CameraSourceType.BROWSER_WEBCAM:
            return BrowserWebcamSource(config, **kwargs)
        if config.source_type == CameraSourceType.UPLOADED_VIDEO:
            return UploadedVideoSource(config, **kwargs)
        raise ValueError(f"Unsupported camera source type: {config.source_type}")

    def test_connection(self, config: CameraConfig) -> Tuple[bool, Optional[str]]:
        """Test connectivity for a camera configuration."""
        result = self.test_connection_details(config)
        return result.ok, result.error_message

    def test_connection_details(self, config: CameraConfig) -> CameraConnectionTestResult:
        """Return structured diagnostics from a real source connection test."""
        source = self.create(config)
        return source.test_connection_details()
