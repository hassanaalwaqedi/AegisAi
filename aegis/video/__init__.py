"""
AegisAI Video Module

Provides video input/output handling for files and camera streams.
"""

from aegis.video.source import VideoSource
from aegis.video.writer import VideoWriter
from aegis.video.rtsp_source import RTSPSource, CameraHealth, CameraStats
from aegis.video.camera_manager import CameraManager, CameraConfig, CameraEvent

__all__ = [
    "VideoSource",
    "VideoWriter",
    "RTSPSource",
    "CameraHealth",
    "CameraStats",
    "CameraManager",
    "CameraConfig",
    "CameraEvent",
]
