"""
AegisAI - Camera Source Factory

Creates the appropriate camera source based on CameraSourceType.
"""

from __future__ import annotations

from typing import Optional, Tuple

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
            return HTTPCameraSource(config, **kwargs)
        if config.source_type == CameraSourceType.BROWSER_WEBCAM:
            return BrowserWebcamSource(config, **kwargs)
        if config.source_type == CameraSourceType.UPLOADED_VIDEO:
            return UploadedVideoSource(config, **kwargs)
        raise ValueError(f"Unsupported camera source type: {config.source_type}")

    def test_connection(self, config: CameraConfig) -> Tuple[bool, Optional[str]]:
        """Test connectivity for a camera configuration."""
        source = self.create(config)
        return source.test_connection()
