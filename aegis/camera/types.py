"""
AegisAI - Camera Types

Enums, dataclasses, and type aliases used across the camera subsystem.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import urlparse, urlunparse

import numpy as np

logger = logging.getLogger(__name__)

# Type aliases for callbacks
FrameCallback = Callable[[str, np.ndarray], None]
StatusCallback = Callable[[str, "CameraConnectionStatus", Optional[str]], None]


class CameraSourceType(str, Enum):
    LOCAL_DEVICE = "LOCAL_DEVICE"
    RTSP_STREAM = "RTSP_STREAM"
    HTTP_STREAM = "HTTP_STREAM"
    BROWSER_WEBCAM = "BROWSER_WEBCAM"
    UPLOADED_VIDEO = "UPLOADED_VIDEO"


class CameraConnectionStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    CONNECTING = "connecting"
    RECONNECTING = "reconnecting"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class CameraConfig:
    """Configuration for a single camera source."""

    camera_id: str
    source_type: CameraSourceType
    name: Optional[str] = None
    location: Optional[str] = None
    enabled: bool = True
    url: Optional[str] = None
    device_index: Optional[int] = None
    upload_path: Optional[str] = None
    video_id: Optional[str] = None
    connection_timeout: float = 5.0
    max_retries: int = 10
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_public_dict(self) -> Dict[str, Any]:
        from aegis.camera.utils import mask_url
        return {
            "camera_id": self.camera_id,
            "source_type": self.source_type.value,
            "name": self.name,
            "location": self.location,
            "enabled": self.enabled,
            "url": mask_url(self.url),
            "device_index": self.device_index,
            "video_id": self.video_id,
            "connection_timeout": self.connection_timeout,
            "max_retries": self.max_retries,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def to_private_dict(self) -> Dict[str, Any]:
        data = self.to_public_dict()
        data["source_type"] = self.source_type.value
        data["url"] = self.url
        data["upload_path"] = self.upload_path
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CameraConfig":
        data = dict(data)
        data["source_type"] = CameraSourceType(data["source_type"])
        return cls(**data)


@dataclass
class CameraRuntimeStatus:
    """Runtime status snapshot of a camera source."""

    camera_id: str
    status: CameraConnectionStatus
    source_type: CameraSourceType
    error_message: Optional[str] = None
    frames_received: int = 0
    frames_dropped: int = 0
    reconnect_count: int = 0
    fps: float = 0.0
    width: Optional[int] = None
    height: Optional[int] = None
    last_frame_time: Optional[str] = None
    connected_since: Optional[str] = None
    running: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "camera_id": self.camera_id,
            "status": self.status.value,
            "source_type": self.source_type.value,
            "error_message": self.error_message,
            "frames_received": self.frames_received,
            "frames_dropped": self.frames_dropped,
            "reconnect_count": self.reconnect_count,
            "fps": round(self.fps, 2),
            "width": self.width,
            "height": self.height,
            "last_frame_time": self.last_frame_time,
            "connected_since": self.connected_since,
            "running": self.running,
        }
