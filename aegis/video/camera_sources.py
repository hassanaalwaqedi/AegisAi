"""
AegisAI production camera source system.

DEPRECATION NOTICE: The camera source classes have moved to ``aegis.camera``.
This module re-exports them for backward compatibility. New code should import
directly from ``aegis.camera``.

The ``FrameIngestionService`` class remains here until it is extracted into
``aegis.pipeline`` in Phase 1.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Backward-compatible re-exports from aegis.camera
# ---------------------------------------------------------------------------
from aegis.camera.types import (  # noqa: F401
    CameraSourceType,
    CameraConnectionStatus,
    CameraConfig,
    CameraRuntimeStatus,
    FrameCallback as FrameCallback,
    StatusCallback as StatusCallback,
)
from aegis.camera.base import BaseCameraSource  # noqa: F401
from aegis.camera.sources import (  # noqa: F401
    OpenCVCameraSource,
    RTSPCameraSource,
    HTTPCameraSource,
    BrowserWebcamSource,
    UploadedVideoSource,
)
from aegis.camera.factory import CameraSourceFactory  # noqa: F401
from aegis.camera.registry import CameraRegistry  # noqa: F401
from aegis.camera.manager import (  # noqa: F401
    MultiCameraPipelineManager,
    CameraHealthMonitor,
)
from aegis.camera.utils import (  # noqa: F401
    mask_url as _mask_url,
    safe_camera_id as _safe_camera_id,
    decode_base64_frame as _decode_base64_frame,
    validate_stream_url as _validate_stream_url,
    frame_to_data_url,
)

import base64
import json
import logging
import re
import threading
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Deque, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

import cv2
import numpy as np

from aegis.api.state import get_state
from aegis.explain import EvidenceExplainer
from aegis.video.youtube_resolver import is_youtube_url, resolve_youtube_stream

logger = logging.getLogger(__name__)

FrameCallback = Callable[[str, np.ndarray], None]
StatusCallback = Callable[[str, "CameraConnectionStatus", Optional[str]], None]


@dataclass(frozen=True)
class EventSnapshot:
    """Result of writing one alert-triggering keyframe to local evidence storage."""

    path: Optional[str]
    status: str


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


def _mask_url(raw_url: Optional[str]) -> Optional[str]:
    if not raw_url:
        return raw_url

    parsed = urlparse(raw_url)
    if not parsed.username and not parsed.password:
        return raw_url

    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"

    if parsed.username:
        netloc = f"{parsed.username}:****@{host}"
    else:
        netloc = host

    return urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))


def _safe_camera_id(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip())
    normalized = normalized.strip("-_")
    if not normalized:
        raise ValueError("camera_id must contain at least one letter or number")
    return normalized[:80]


def _decode_base64_frame(frame: str) -> np.ndarray:
    if "," in frame:
        frame = frame.split(",", 1)[1]
    try:
        frame_bytes = base64.b64decode(frame, validate=True)
    except Exception as exc:
        raise ValueError("Frame is not valid base64 image data") from exc

    image_array = np.frombuffer(frame_bytes, np.uint8)
    decoded = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    if decoded is None:
        raise ValueError("Frame could not be decoded as an image")
    return decoded


@dataclass
class CameraConfig:
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
        return {
            "camera_id": self.camera_id,
            "source_type": self.source_type.value,
            "name": self.name,
            "location": self.location,
            "enabled": self.enabled,
            "url": _mask_url(self.url),
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
        raise NotImplementedError(f"{self.config.source_type.value} does not accept pushed frames")

    def test_connection(self) -> Tuple[bool, Optional[str]]:
        raise NotImplementedError

    def check_health(self, stale_after_seconds: float = 5.0) -> None:
        if not self._running:
            return
        if self._last_frame_time is None:
            return
        elapsed = (datetime.utcnow() - self._last_frame_time).total_seconds()
        if elapsed > stale_after_seconds and self._status == CameraConnectionStatus.ONLINE:
            self._set_status(CameraConnectionStatus.RECONNECTING, "No frames received recently")

    def get_frame(self, timeout: float = 0.0) -> Optional[np.ndarray]:
        del timeout
        with self._frame_lock:
            return None if self._latest_frame is None else self._latest_frame.copy()

    def get_snapshot_jpeg(self) -> Optional[bytes]:
        with self._frame_lock:
            return self._latest_jpeg

    def get_status(self) -> CameraRuntimeStatus:
        fps = sum(self._fps_samples) / len(self._fps_samples) if self._fps_samples else 0.0
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
            last_frame_time=self._last_frame_time.isoformat() if self._last_frame_time else None,
            connected_since=self._connected_since.isoformat() if self._connected_since else None,
            running=self._running,
        )

    def _set_status(self, status: CameraConnectionStatus, error: Optional[str] = None) -> None:
        changed = status != self._status or error != self._error_message
        self._status = status
        self._error_message = error
        if status == CameraConnectionStatus.ONLINE and self._connected_since is None:
            self._connected_since = datetime.utcnow()
        if changed:
            logger.info("Camera %s status=%s error=%s", self.camera_id, status.value, error)
            if self._on_status_change:
                self._on_status_change(self.camera_id, status, error)

    def _publish_frame(self, frame: np.ndarray, notify_pipeline: bool = True) -> None:
        now = time.time()
        if self._last_publish_ts is not None:
            delta = max(now - self._last_publish_ts, 0.001)
            self._fps_samples.append(1.0 / delta)
        self._last_publish_ts = now

        height, width = frame.shape[:2]
        encode_ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
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


class _OpenCVLoopCameraSource(BaseCameraSource):
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
        self._thread = threading.Thread(target=self._capture_loop, daemon=True, name=f"camera-{self.camera_id}")
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
            capture.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, self.config.connection_timeout * 1000)
            capture.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, self.config.connection_timeout * 1000)
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
                self._set_status(CameraConnectionStatus.RECONNECTING if retries <= self.config.max_retries else CameraConnectionStatus.ERROR, message)
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

            while self._running and self._capture is not None and self._capture.isOpened():
                ok, frame = self._capture.read()
                if not ok or frame is None:
                    if self._finite:
                        self._set_status(CameraConnectionStatus.STOPPED, "Video processing completed")
                        self._running = False
                        break
                    failures += 1
                    self._frames_dropped += 1
                    if failures >= 5:
                        self._set_status(CameraConnectionStatus.RECONNECTING, "Frame reads failed")
                        self._release_capture()
                        break
                    continue

                failures = 0
                self._pace_frame(frame_interval)
                self._publish_frame(frame)

            self._release_capture()

        self._release_capture()
        if self._status not in (CameraConnectionStatus.ERROR, CameraConnectionStatus.STOPPED):
            self._set_status(CameraConnectionStatus.OFFLINE)

    def _release_capture(self) -> None:
        if self._capture is not None:
            try:
                self._capture.release()
            except Exception:
                pass
            self._capture = None

    def _get_frame_interval(self, capture: Optional[cv2.VideoCapture]) -> Optional[float]:
        del capture
        return None

    def _fps_interval(self, fps: Optional[float]) -> Optional[float]:
        if fps is None or fps <= 0:
            return None
        return 1.0 / min(float(fps), self.MAX_PLAYBACK_FPS)

    def _capture_fps_interval(self, capture: Optional[cv2.VideoCapture]) -> Optional[float]:
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


class OpenCVCameraSource(_OpenCVLoopCameraSource):
    def __init__(self, config: CameraConfig, **kwargs):
        if config.device_index is None:
            raise ValueError("LOCAL_DEVICE requires device_index")
        super().__init__(config, capture_source=config.device_index, finite=False, **kwargs)


class RTSPCameraSource(_OpenCVLoopCameraSource):
    def __init__(self, config: CameraConfig, **kwargs):
        _validate_stream_url(config.url, {"rtsp", "rtsps"}, "RTSP_STREAM")
        super().__init__(config, capture_source=config.url, finite=False, **kwargs)


class HTTPCameraSource(_OpenCVLoopCameraSource):
    def __init__(self, config: CameraConfig, **kwargs):
        _validate_stream_url(config.url, {"http", "https"}, "HTTP_STREAM")
        self._youtube_page_url = config.url if is_youtube_url(config.url) else None
        super().__init__(config, capture_source=config.url, finite=False, **kwargs)

    def _resolve_capture_source(self) -> str:
        if not self._youtube_page_url:
            return str(self.config.url)

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

    def _get_frame_interval(self, capture: Optional[cv2.VideoCapture]) -> Optional[float]:
        if not self._youtube_page_url:
            return None
        metadata_fps = self.config.metadata.get("resolved_fps")
        interval = self._fps_interval(float(metadata_fps)) if metadata_fps else None
        return interval or self._capture_fps_interval(capture) or self._fps_interval(30.0)


class UploadedVideoSource(_OpenCVLoopCameraSource):
    def __init__(self, config: CameraConfig, **kwargs):
        if not config.upload_path or not Path(config.upload_path).exists():
            raise ValueError("UPLOADED_VIDEO requires an existing upload_path")
        super().__init__(config, capture_source=config.upload_path, finite=True, **kwargs)

    def _get_frame_interval(self, capture: Optional[cv2.VideoCapture]) -> Optional[float]:
        return self._capture_fps_interval(capture) or self._fps_interval(30.0)


class BrowserWebcamSource(BaseCameraSource):
    def start(self) -> None:
        self._running = True
        self._set_status(CameraConnectionStatus.CONNECTING, "Waiting for browser frames")

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
            self._set_status(CameraConnectionStatus.CONNECTING, "Waiting for browser frames")
            return
        elapsed = (datetime.utcnow() - self._last_frame_time).total_seconds()
        if elapsed > stale_after_seconds:
            self._set_status(CameraConnectionStatus.RECONNECTING, "Browser frames stopped")


def _validate_stream_url(raw_url: Optional[str], allowed_schemes: set[str], label: str) -> None:
    if not raw_url:
        raise ValueError(f"{label} requires url")
    parsed = urlparse(raw_url)
    if parsed.scheme.lower() not in allowed_schemes:
        allowed = ", ".join(sorted(allowed_schemes))
        raise ValueError(f"{label} URL must use one of: {allowed}")
    if not parsed.hostname:
        raise ValueError(f"{label} URL must include a host")


class CameraSourceFactory:
    def create(
        self,
        config: CameraConfig,
        on_frame: Optional[FrameCallback] = None,
        on_status_change: Optional[StatusCallback] = None,
    ) -> BaseCameraSource:
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
        source = self.create(config)
        return source.test_connection()


class CameraRegistry:
    def __init__(self, storage_path: Path | str = "data/cameras/cameras.json"):
        self._storage_path = Path(storage_path)
        self._lock = threading.RLock()
        self._configs: Dict[str, CameraConfig] = {}
        self._load()

    def list(self) -> List[CameraConfig]:
        with self._lock:
            return list(self._configs.values())

    def get(self, camera_id: str) -> Optional[CameraConfig]:
        with self._lock:
            return self._configs.get(camera_id)

    def save(self, config: CameraConfig) -> CameraConfig:
        with self._lock:
            config.camera_id = _safe_camera_id(config.camera_id)
            config.updated_at = datetime.utcnow().isoformat()
            self._configs[config.camera_id] = config
            self._persist()
            return config

    def delete(self, camera_id: str) -> bool:
        with self._lock:
            if camera_id not in self._configs:
                return False
            del self._configs[camera_id]
            self._persist()
            return True

    def _load(self) -> None:
        if not self._storage_path.exists():
            return
        try:
            raw = json.loads(self._storage_path.read_text(encoding="utf-8"))
            self._configs = {
                item["camera_id"]: CameraConfig.from_dict(item)
                for item in raw.get("cameras", [])
            }
        except Exception as exc:
            logger.error("Failed to load camera registry: %s", exc)
            self._configs = {}

    def _persist(self) -> None:
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"cameras": [config.to_private_dict() for config in self._configs.values()]}
        self._storage_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class FrameIngestionService:
    """Runs real detection, tracking, risk scoring, state updates, and event storage."""

    def __init__(self, event_buffer_size: int = 1000):
        self._detector = None
        self._detector_lock = threading.Lock()
        self._trackers: Dict[str, Any] = {}
        self._history_managers: Dict[str, Any] = {}
        self._motion_analyzers: Dict[str, Any] = {}
        self._behavior_analyzers: Dict[str, Any] = {}
        self._crowd_analyzers: Dict[str, Any] = {}
        self._risk_engines: Dict[str, Any] = {}
        self._proximity_engines: Dict[str, Any] = {}
        self._association_engines: Dict[str, Any] = {}
        self._weapon_aggression_engines: Dict[str, Any] = {}
        self._frame_counters: Dict[str, int] = {}
        # A tracker reset can reuse a small numeric ID.  Persisted observations
        # therefore carry a new source epoch instead of pretending that IDs
        # from separate camera sessions are the same entity.
        self._camera_source_epochs: Dict[str, str] = {}
        self._camera_start_ts: Dict[str, float] = {}
        self._high_risk_frames: Dict[str, int] = {}
        self._fallback_alert_cooldowns: Dict[str, float] = {}
        # Per-camera metadata fingerprints let edited zones take effect without
        # restarting the camera pipeline.
        self._configured_zones: Dict[str, str] = {}
        self._alert_manager = None
        self._event_repository = None
        self._vehicle_enrichment_service = None
        self._vehicle_enrichment_lock = threading.Lock()
        self._events: Deque[Dict[str, Any]] = deque(maxlen=event_buffer_size)
        self._detections: Deque[Dict[str, Any]] = deque(maxlen=event_buffer_size)
        self._emitted_detection_events: set[str] = set()
        self._lock = threading.RLock()
        self._total_frames = 0
        self._total_detections = 0
        self._total_alerts = 0
        self._high_risk_count = 0
        self._last_processing_ts = time.time()
        self._evidence_explainer = EvidenceExplainer()

    def process_frame(
        self,
        camera_id: str,
        frame: np.ndarray,
        camera_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        camera_metadata = camera_metadata or {}
        camera_name = camera_metadata.get("camera_name") or camera_metadata.get("name")
        with self._lock:
            # Capture the start timestamp once for this in-flight frame.  A
            # camera stop may concurrently clear the per-camera maps, but the
            # worker must finish safely instead of indexing a removed key.
            start_timestamp = self._camera_start_ts.setdefault(camera_id, time.time())
            source_epoch = self._camera_source_epochs.setdefault(camera_id, uuid.uuid4().hex)
            self._frame_counters[camera_id] = self._frame_counters.get(camera_id, 0) + 1
            frame_id = self._frame_counters[camera_id]

        logger.debug("Frame received camera_id=%s frame_id=%s shape=%s", camera_id, frame_id, frame.shape)

        detector = self._get_detector()
        tracker = self._get_tracker(camera_id)
        history_manager = self._get_history_manager(camera_id)
        motion_analyzer = self._get_motion_analyzer(camera_id)
        behavior_analyzer = self._get_behavior_analyzer(camera_id)
        crowd_analyzer = self._get_crowd_analyzer(camera_id)
        risk_engine = self._get_risk_engine(camera_id, frame, camera_metadata)
        proximity_engine = self._get_proximity_engine(camera_id)
        association_engine = self._get_association_engine(camera_id)
        weapon_aggression_engine = self._get_weapon_aggression_engine(camera_id)

        detections = detector.detect(frame)
        detection_classes = [getattr(det, "class_name", "unknown") for det in detections]
        logger.debug(
            "Detections camera_id=%s frame_id=%s count=%s classes=%s",
            camera_id,
            frame_id,
            len(detections),
            detection_classes,
        )

        tracks = tracker.update(detections, frame)
        now = datetime.utcnow()
        timestamp_seconds = time.time() - start_timestamp

        history_manager.update(tracks, frame_id=frame_id, timestamp=timestamp_seconds)
        motion_states = motion_analyzer.analyze_all(history_manager)
        behaviors = behavior_analyzer.analyze_all(history_manager, motion_states)
        crowd_metrics = crowd_analyzer.analyze(tracks, frame.shape)

        from aegis.analysis.analysis_types import TrackAnalysis

        track_analyses = []
        for track in tracks:
            history = history_manager.get_history(track.track_id)
            if history is None:
                continue
            motion = motion_states.get(track.track_id)
            behavior = behaviors.get(track.track_id)
            if motion is None or behavior is None:
                continue
            current = history.current_position
            track_analyses.append(
                TrackAnalysis(
                    track_id=track.track_id,
                    class_id=track.class_id,
                    class_name=track.class_name,
                    motion=motion,
                    behavior=behavior,
                    history_length=history.history_length,
                    time_tracked=history.duration,
                    current_position=(current.x, current.y) if current else (0.0, 0.0),
                    current_bbox=track.bbox,
                )
            )

        risk_summary = risk_engine.compute_frame_risks(
            track_analyses=track_analyses,
            crowd_metrics=crowd_metrics,
            frame_id=frame_id,
            timestamp=timestamp_seconds,
        )
        proximity = proximity_engine.assess(tracks, frame_id=frame_id)
        associations = association_engine.assess(tracks, frame_id=frame_id)
        risk_by_track = {risk.track_id: risk for risk in risk_summary.track_risks}
        analysis_by_track = {analysis.track_id: analysis for analysis in track_analyses}
        association_by_person = {item.person_track_id: item.to_dict() for item in associations if item.association_type != "none"}
        association_by_weapon = {item.weapon_track_id: item.to_dict() for item in associations if item.association_type != "none"}
        threat_contexts = weapon_aggression_engine.assess(
            tracks=tracks,
            associations=associations,
            analyses=analysis_by_track,
            frame_id=frame_id,
        )
        threat_by_track: Dict[str, Dict[str, Any]] = {}
        for context in threat_contexts:
            context_payload = context.to_dict()
            context_track_ids = [context.armed_person_track_id]
            if context.weapon_track_id:
                context_track_ids.append(context.weapon_track_id)
            for context_track_id in context_track_ids:
                current = threat_by_track.get(str(context_track_id))
                if current is None or float(context_payload["risk_score"]) > float(current["risk_score"]):
                    threat_by_track[str(context_track_id)] = context_payload

        logger.debug("Tracks camera_id=%s frame_id=%s count=%s", camera_id, frame_id, len(tracks))

        track_payloads: List[Dict[str, Any]] = []
        frame_detected_classes = sorted({name for name in detection_classes})
        risk_distribution = {"LOW": 0, "CANDIDATE_MEDIUM": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
        max_risk_level = "LOW"
        max_risk_score = 0.0
        generated_events: List[Dict[str, Any]] = []

        for track in tracks:
            track_key = f"{camera_id}:{getattr(track, 'track_id', 'untracked')}"
            bbox = tuple(getattr(track, "bbox", (0, 0, 0, 0)))
            class_name = getattr(track, "class_name", "unknown")
            object_category = getattr(track, "object_category", "generic")
            is_person = bool(getattr(track, "is_person", False))
            is_weapon = bool(getattr(track, "is_weapon", False))
            is_vehicle = bool(getattr(track, "is_vehicle", False)) or str(object_category).lower() == "vehicle"
            detector_model_source = getattr(track, "model_source", "") or self.get_model_capabilities().get("model_name", "")
            raw_track_id = str(getattr(track, "track_id", ""))
            association = association_by_person.get(raw_track_id) or association_by_weapon.get(raw_track_id)
            threat_context = threat_by_track.get(raw_track_id)
            analysis = analysis_by_track.get(track.track_id)
            risk_score_obj = risk_by_track.get(track.track_id)
            risk_score = float(risk_score_obj.score) if risk_score_obj else 0.0
            risk_level = risk_score_obj.level.value if risk_score_obj else "LOW"
            explanation = risk_score_obj.explanation.to_string() if risk_score_obj else f"{track.class_name} detected; no elevated risk signals"
            factors = [factor.display_name for factor in risk_score_obj.explanation.factors if factor.weighted_value > 0.01] if risk_score_obj else []
            behavior_labels = self._behavior_labels(analysis.behavior if analysis else None)
            raw_behavior_labels = list(behavior_labels)
            motion_confirmed = self._motion_behavior_confirmed(analysis)
            if not motion_confirmed:
                behavior_labels = [
                    label for label in behavior_labels
                    if label not in {"running", "erratic_motion", "direction_reversal"}
                ] or ["normal"]
                motion_factor_names = {"Running", "Erratic Movement", "Direction Reversal"}
                factors = [factor for factor in factors if factor not in motion_factor_names]
                if risk_score_obj and any(label in {"running", "erratic_motion", "direction_reversal"} for label in raw_behavior_labels):
                    risk_score = 0.25
                    risk_level = "CANDIDATE_MEDIUM"
                    explanation = "Motion candidate detected from bounding-box movement. Candidate movement requires further temporal confirmation."
            movement_state = self._movement_state(analysis.motion if analysis else None)
            if movement_state == "running" and not motion_confirmed:
                movement_state = "moving" if analysis and analysis.motion.is_moving else "tracked"

            risk_score, risk_level, explanation, factors = self._apply_frame_rules(
                track=track,
                analysis=analysis,
                base_score=risk_score,
                base_level=risk_level,
                base_explanation=explanation,
                factors=factors,
                behavior_labels=behavior_labels,
                crowd_metrics=crowd_metrics,
                proximity=proximity,
            )
            evidence = self._build_evidence(
                track=track,
                bbox=bbox,
                risk_level=risk_level,
                risk_score=risk_score,
                behavior_labels=behavior_labels,
                raw_behavior_labels=raw_behavior_labels,
                factors=factors,
                explanation=explanation,
                motion_confirmed=motion_confirmed,
                frame_detected_classes=frame_detected_classes,
                association=association,
                threat_context=threat_context,
            )
            risk_level = evidence["risk_level"]
            risk_score = evidence["risk_score"]
            explanation = evidence["explanation"]
            factors = evidence["reason_codes"]
            # This read only carries the evaluated zone into the evidence
            # record. It does not change RiskEngine scoring or alert policy.
            zone_manager = getattr(risk_engine, "zone_manager", None)
            zone_context = zone_manager.get_context(bbox=bbox) if zone_manager else None
            zone_id = (
                zone_context.zone.zone_id
                if zone_context and zone_context.in_zone and zone_context.zone
                else None
            )
            zone_name = zone_context.zone_name if zone_context and zone_context.in_zone else None

            # This optional sidecar is intentionally after normal detection,
            # tracking, and risk computation. It cannot influence their result.
            vehicle_enrichment = None
            if is_vehicle:
                try:
                    vehicle_enrichment = self._get_vehicle_enrichment_service().enrich(
                        camera_id=camera_id,
                        track_id=raw_track_id,
                        frame=frame,
                        bbox=bbox,
                        high_priority=risk_level in {"HIGH", "CRITICAL"},
                        frame_token=f"{camera_id}:{frame_id}",
                    ).to_public_dict()
                except Exception:
                    logger.exception("Vehicle enrichment sidecar failed camera_id=%s track_id=%s", camera_id, raw_track_id)
                    vehicle_enrichment = {"status": "unavailable", "reason": "enrichment_error"}

            risk_distribution[risk_level] = risk_distribution.get(risk_level, 0) + 1
            if risk_score > max_risk_score:
                max_risk_score = risk_score
                max_risk_level = risk_level

            payload = {
                "camera_id": camera_id,
                "camera_name": camera_name,
                "source_epoch": source_epoch,
                "track_id": track_key,
                "raw_track_id": getattr(track, "track_id", None),
                "class_name": class_name,
                "class_id": getattr(track, "class_id", 0),
                "object_category": object_category,
                "is_person": is_person,
                "is_vehicle": is_vehicle,
                "is_weapon": is_weapon,
                "confidence": float(getattr(track, "confidence", 0.0)),
                "bbox": list(bbox),
                "zone_id": zone_id,
                "zone_name": zone_name,
                "model_source": evidence["model_source"],
                "detection_model_source": detector_model_source,
                "risk_level": risk_level,
                "risk_score": risk_score,
                "behaviors": behavior_labels,
                "behavior_labels": behavior_labels,
                "risk_explanation": explanation,
                "risk_factors": factors,
                "evidence_type": evidence["evidence_type"],
                "verification_status": evidence["verification_status"],
                "reason_codes": evidence["reason_codes"],
                "visual_evidence": evidence["visual_evidence"],
                "weapon_class": evidence["weapon_class"],
                "weapon_confidence": evidence["weapon_confidence"],
                "person_track_id": evidence["person_track_id"],
                "weapon_track_id": evidence["weapon_track_id"],
                "association_type": evidence["association_type"],
                "association_score": evidence["association_score"],
                "stable_frames": evidence["stable_frames"],
                "evidence_objects": evidence["evidence_objects"],
                "threat_event_type": evidence.get("threat_event_type"),
                "nearby_person_track_id": evidence.get("nearby_person_track_id"),
                "threat_context": evidence.get("threat_context"),
                "vehicle_enrichment": vehicle_enrichment,
                "detected_classes": frame_detected_classes,
                "movement_state": movement_state,
                "speed": float(analysis.motion.speed_smoothed) if analysis else 0.0,
                "time_tracked": float(analysis.time_tracked) if analysis else 0.0,
                "duration_seconds": float(analysis.time_tracked) if analysis else 0.0,
                "first_seen": now.isoformat(),
                "total_seen_count": 1,
                "last_seen": now.isoformat(),
                "frame_number": frame_id,
                "frame_id": frame_id
            }
            track_payloads.append(payload)
            self._detections.append(payload)
            get_state().update_track(
                track_id=track_key,
                class_name=payload["class_name"],
                object_category=payload["object_category"],
                is_person=payload["is_person"],
                is_vehicle=payload["is_vehicle"],
                is_weapon=payload["is_weapon"],
                risk_level=payload["risk_level"],
                risk_score=float(payload["risk_score"]),
                zone=camera_id,
                behaviors=payload["behaviors"],
                time_tracked=payload["time_tracked"],
                camera_id=camera_id,
                confidence=payload["confidence"],
                bbox=payload["bbox"],
                risk_explanation=explanation,
                detected_classes=frame_detected_classes,
                evidence_type=payload["evidence_type"],
                model_source=payload["model_source"],
                verification_status=payload["verification_status"],
                reason_codes=payload["reason_codes"],
                visual_evidence=payload["visual_evidence"],
                weapon_class=payload["weapon_class"],
                weapon_confidence=payload["weapon_confidence"],
                person_track_id=payload["person_track_id"],
                weapon_track_id=payload["weapon_track_id"],
                association_type=payload["association_type"],
                association_score=payload["association_score"],
                stable_frames=payload["stable_frames"],
                evidence_objects=payload["evidence_objects"],
                vehicle_enrichment=payload["vehicle_enrichment"],
                movement_state=movement_state,
                last_seen=payload["last_seen"],
            )
            registry_entry = self._registry_entry(track_key)
            if registry_entry:
                payload["first_seen"] = registry_entry.get("first_seen")
                payload["duration_seconds"] = registry_entry.get("duration_seconds")
                payload["total_seen_count"] = registry_entry.get("total_seen_count")

        # Persist raw track/relationship measurements before generating an
        # alert. A cooldown may suppress notification, but it must not erase
        # the observations needed to explain or later reassess the scene.
        self._persist_frame_observations(
            camera_id=camera_id,
            source_epoch=source_epoch,
            frame_id=frame_id,
            captured_at=now,
            track_payloads=track_payloads,
        )

        for payload in track_payloads:
            # Composite threat context is copied onto the weapon track for
            # evidence display, but only the actor/person track may own the
            # operational event. This keeps top-level bbox/track identity
            # deterministic regardless of tracker output order.
            if not self._is_primary_threat_track(payload):
                continue
            event_payload = self._maybe_generate_alert(
                camera_id=camera_id,
                track_payload=payload,
                frame_number=frame_id,
                timestamp=now,
                frame=frame,
            )
            if event_payload:
                generated_events.append(event_payload)
            confirmed_threat = bool(payload.get("threat_context")) and (
                payload.get("risk_level") in {"HIGH", "CRITICAL"}
                and payload.get("verification_status") in {"confirmed", "critical"}
            )
            if event_payload is None and not confirmed_threat:
                detection_event = self._maybe_generate_detection_event(
                    camera_id=camera_id,
                    track_payload=payload,
                    frame_number=frame_id,
                    timestamp=now,
                )
                if detection_event:
                    generated_events.append(detection_event)

        logger.debug(
            "Risk scores camera_id=%s frame_id=%s scores=%s",
            camera_id,
            frame_id,
            [(item["track_id"], item["risk_level"], round(item["risk_score"], 3)) for item in track_payloads],
        )

        with self._lock:
            self._total_frames += 1
            self._total_detections += len(track_payloads)
            person_count = sum(1 for t in track_payloads if t["class_name"].lower() == "person")
            vehicle_count = sum(1 for t in track_payloads if t["class_name"].lower() in {"car", "truck", "bus", "motorcycle", "bicycle"})
            weapon_count = sum(1 for t in track_payloads if t.get("is_weapon"))
            association_count = sum(1 for t in track_payloads if t.get("association_type") in {"near", "overlap", "contained"})
            critical_association_count = sum(1 for t in track_payloads if t.get("verification_status") == "critical")
            detections_by_class: Dict[str, int] = {}
            for item in track_payloads:
                name = str(item.get("class_name", "unknown")).lower()
                detections_by_class[name] = detections_by_class.get(name, 0) + 1
            current_ts = time.time()
            fps = 1.0 / max(current_ts - self._last_processing_ts, 0.001)
            self._last_processing_ts = current_ts
            model_info = self.get_model_capabilities()

            get_state().update_status(
                frames=self._total_frames,
                fps=fps,
                active_tracks=len(track_payloads),
                detections=self._total_detections,
                anomalies=sum(1 for t in track_payloads if t["behaviors"] and t["behaviors"] != ["normal"]),
                total_alerts=self._total_alerts,
                high_risk_count=self._high_risk_count,
                max_risk_level=max_risk_level,
                max_risk_score=max_risk_score,
                model_name=model_info["model_name"],
                supported_classes=model_info["supported_classes"],
                weapon_detection_supported=model_info["weapon_detection_supported"],
                person_detector=model_info.get("person_detector"),
                weapon_detector=model_info.get("weapon_detector"),
                action_recognition_supported=model_info["action_recognition_supported"],
                pose_estimation_supported=model_info["pose_estimation_supported"],
                semantic_verification_supported=model_info["semantic_verification_supported"],
            )
            get_state().update_statistics(
                person_count=person_count,
                vehicle_count=vehicle_count,
                weapon_count=weapon_count,
                active_detections_count=len(track_payloads),
                detections_by_class=detections_by_class,
                crowd_detected=person_count >= 10,
                max_density=crowd_metrics.max_density,
                risk_distribution=risk_distribution,
                association_count=association_count,
                critical_association_count=critical_association_count,
            )

        logger.debug(
            "Generated alerts camera_id=%s frame_id=%s count=%s",
            camera_id,
            frame_id,
            len(generated_events),
        )

        return {
            "camera_id": camera_id,
            "frame_id": frame_id,
            "frame_number": frame_id,
            "timestamp": now.isoformat(),
            "detections": track_payloads,
            "risk": {
                "risk_score": round(max_risk_score, 3),
                "risk_level": max_risk_level,
                "triggers": sorted({factor for item in track_payloads for factor in item.get("risk_factors", [])}),
                "should_escalate": max_risk_level in {"HIGH", "CRITICAL"},
                "explanation": self._frame_explanation(track_payloads),
                "verification_status": self._frame_verification_status(track_payloads),
            },
            "events": generated_events,
            "event": generated_events[-1] if generated_events else None,
            "model": self.get_model_capabilities(),
        }

    def get_camera_events(self, camera_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return [event for event in list(self._events) if event.get("camera_id") == camera_id][-limit:]

    def get_camera_detections(self, camera_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return [item for item in list(self._detections) if item.get("camera_id") == camera_id][-limit:]

    def reset_camera(self, camera_id: str) -> None:
        """Drop per-camera temporal state without deleting durable evidence."""
        camera_prefix = f"{camera_id}:"
        with self._lock:
            for mapping in (
                self._trackers,
                self._history_managers,
                self._motion_analyzers,
                self._behavior_analyzers,
                self._crowd_analyzers,
                self._risk_engines,
                self._proximity_engines,
                self._association_engines,
                self._weapon_aggression_engines,
            ):
                mapping.pop(camera_id, None)
            self._frame_counters.pop(camera_id, None)
            self._camera_source_epochs.pop(camera_id, None)
            self._camera_start_ts.pop(camera_id, None)
            self._configured_zones.pop(camera_id, None)
            self._high_risk_frames = {
                key: value
                for key, value in self._high_risk_frames.items()
                if not str(key).startswith(camera_prefix)
            }
            self._fallback_alert_cooldowns = {
                key: value
                for key, value in self._fallback_alert_cooldowns.items()
                if not str(key).startswith(camera_prefix)
            }
            self._emitted_detection_events = {
                key for key in self._emitted_detection_events
                if not str(key).startswith(camera_prefix)
            }
        if self._alert_manager is not None and hasattr(self._alert_manager, "clear_cooldowns"):
            self._alert_manager.clear_cooldowns(prefix=camera_prefix)

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "frames_processed": self._total_frames,
                "total_detections": self._total_detections,
                "camera_count": len(self._frame_counters),
                "active_detections_count": len(get_state().get_tracks()),
                "object_registry_count": len(get_state().get_object_registry()),
                "total_alerts": self._total_alerts,
                "high_risk_count": self._high_risk_count,
                "model": self.get_model_capabilities(),
            }

    def get_model_capabilities(self) -> Dict[str, Any]:
        detector = self._detector
        if detector is not None and hasattr(detector, "get_model_capabilities"):
            return detector.get_model_capabilities()

        from config import DetectionConfig

        config = DetectionConfig()
        base_detector_available = Path(config.model_path).is_file()
        class_names = dict(config.CLASS_NAMES)
        target_classes = tuple(config.target_classes)
        configured_person_classes = [
            class_names.get(class_id, f"class_{class_id}")
            for class_id in sorted(set(target_classes))
        ]
        person_supported = configured_person_classes if base_detector_available else []
        weapon_supported = list(config.weapon_model_class_names.values())
        base_weapon_supported = ([
            class_names.get(class_id, f"class_{class_id}")
            for class_id in sorted(set(target_classes) & set(config.weapon_classes))
        ] if base_detector_available else [])
        custom_weapon_supported = Path(config.weapon_model_path).is_file()
        available_custom_classes = weapon_supported if custom_weapon_supported else []
        supported_weapon_classes = list(dict.fromkeys([*base_weapon_supported, *available_custom_classes]))
        supported_families = {
            (
                "firearm"
                if str(value).strip().lower().replace("_", " ") in {"gun", "pistol", "firearm", "handgun"}
                else str(value).strip().lower().replace("_", " ")
            )
            for value in supported_weapon_classes
        }
        unsupported_weapon_concepts = []
        if "weapon" not in supported_families:
            unsupported_weapon_concepts.append("generic weapon")
        if "sharp object" not in supported_families:
            unsupported_weapon_concepts.append("generic sharp object")
        if "firearm" not in supported_families:
            unsupported_weapon_concepts.extend(["gun", "pistol"])

        return {
            "model_name": config.model_path,
            "base_detector_available": base_detector_available,
            "supported_classes": list(dict.fromkeys([*person_supported, *available_custom_classes])),
            "supported_weapon_classes": supported_weapon_classes,
            "unsupported_weapon_concepts": unsupported_weapon_concepts,
            "weapon_detection_supported": bool(supported_weapon_classes),
            "person_detector": {
                "model_name": config.model_path,
                "detector_available": base_detector_available,
                "availability": "configured_not_loaded" if base_detector_available else "unavailable",
                "unavailable_reason": None if base_detector_available else f"Base detector weights are unavailable: {config.model_path}",
                "supported_classes": person_supported,
                "weapon_classes": base_weapon_supported,
                "weapon_detection_supported": bool(base_weapon_supported),
            },
            "weapon_detector": {
                "model_name": config.weapon_model_path,
                "supported_classes": weapon_supported,
                "available_classes": available_custom_classes,
                "internal_class_ids": {
                    name: int(config.weapon_internal_class_ids[source_id])
                    for source_id, name in config.weapon_model_class_names.items()
                },
                "weapon_detection_supported": custom_weapon_supported,
                "class_mapping_validated": False,
                "validation_status": "configured_not_loaded" if custom_weapon_supported else "unavailable",
                "limitation": None if custom_weapon_supported else f"Weapon detector weights are unavailable: {config.weapon_model_path}",
            },
            "action_recognition_supported": False,
            "pose_estimation_supported": False,
            "semantic_verification_supported": False,
        }

    def _get_vehicle_enrichment_service(self):
        """Create the optional sidecar lazily, after camera startup succeeds."""
        if self._vehicle_enrichment_service is None:
            with self._vehicle_enrichment_lock:
                if self._vehicle_enrichment_service is None:
                    from aegis.settings import get_settings
                    from aegis.video.vehicle_enrichment import VehicleEnrichmentService

                    self._vehicle_enrichment_service = VehicleEnrichmentService(
                        get_settings().vehicle_enrichment
                    )
        return self._vehicle_enrichment_service

    def _get_detector(self):
        if self._detector is None:
            with self._detector_lock:
                if self._detector is None:
                    from aegis.detection.multi_model_detector import MultiModelDetector

                    self._detector = MultiModelDetector()
        return self._detector

    def _get_tracker(self, camera_id: str):
        if camera_id not in self._trackers:
            from aegis.tracking.bytetrack_tracker import ByteTrackTracker

            self._trackers[camera_id] = ByteTrackTracker()
        return self._trackers[camera_id]

    def _get_history_manager(self, camera_id: str):
        if camera_id not in self._history_managers:
            from aegis.analysis.track_history import TrackHistoryManager

            self._history_managers[camera_id] = TrackHistoryManager(window_size=120)
        return self._history_managers[camera_id]

    def _get_motion_analyzer(self, camera_id: str):
        if camera_id not in self._motion_analyzers:
            from aegis.analysis.motion_analyzer import MotionAnalyzer

            self._motion_analyzers[camera_id] = MotionAnalyzer()
        return self._motion_analyzers[camera_id]

    def _get_behavior_analyzer(self, camera_id: str):
        if camera_id not in self._behavior_analyzers:
            from aegis.analysis.behavior_analyzer import BehaviorAnalyzer

            self._behavior_analyzers[camera_id] = BehaviorAnalyzer()
        return self._behavior_analyzers[camera_id]

    def _get_crowd_analyzer(self, camera_id: str):
        if camera_id not in self._crowd_analyzers:
            from aegis.analysis.crowd_analyzer import CrowdAnalyzer

            self._crowd_analyzers[camera_id] = CrowdAnalyzer()
        return self._crowd_analyzers[camera_id]

    def _get_risk_engine(self, camera_id: str, frame: np.ndarray, metadata: Optional[Dict[str, Any]]):
        if camera_id not in self._risk_engines:
            from aegis.risk.risk_engine import RiskEngine

            self._risk_engines[camera_id] = RiskEngine()
        self._configure_zones(camera_id, self._risk_engines[camera_id], frame, metadata)
        return self._risk_engines[camera_id]

    def _get_proximity_engine(self, camera_id: str):
        if camera_id not in self._proximity_engines:
            from aegis.risk.proximity_risk import ProximityRiskEngine

            self._proximity_engines[camera_id] = ProximityRiskEngine()
        return self._proximity_engines[camera_id]

    def _get_association_engine(self, camera_id: str):
        if camera_id not in self._association_engines:
            from aegis.risk.person_weapon_association import PersonWeaponAssociationEngine

            self._association_engines[camera_id] = PersonWeaponAssociationEngine()
        return self._association_engines[camera_id]

    def _get_weapon_aggression_engine(self, camera_id: str):
        if camera_id not in self._weapon_aggression_engines:
            from aegis.risk.weapon_aggression import WeaponAggressionRiskLayer

            self._weapon_aggression_engines[camera_id] = WeaponAggressionRiskLayer()
        return self._weapon_aggression_engines[camera_id]

    def _get_alert_manager(self):
        if self._alert_manager is None:
            try:
                from aegis.alerts.alert_manager import AlertManager, AlertManagerConfig
                from aegis.alerts.alert_types import AlertChannel

                self._alert_manager = AlertManager(
                    AlertManagerConfig(channels={AlertChannel.FILE, AlertChannel.API})
                )
                try:
                    from aegis.api.routes.alerts import set_alert_manager

                    set_alert_manager(self._alert_manager)
                except Exception:
                    pass
            except Exception as exc:
                logger.warning("Alert manager unavailable: %s", exc)
                self._alert_manager = False
        return self._alert_manager if self._alert_manager is not False else None

    def _configure_zones(
        self,
        camera_id: str,
        risk_engine: Any,
        frame: np.ndarray,
        metadata: Optional[Dict[str, Any]],
    ) -> None:
        metadata = metadata or {}
        zones = metadata.get("restricted_zones") or metadata.get("zones") or []
        try:
            fingerprint = json.dumps(zones, sort_keys=True, default=str)
        except (TypeError, ValueError):
            fingerprint = repr(zones)
        if self._configured_zones.get(camera_id) == fingerprint:
            return

        from aegis.risk.zone_context import Zone, ZoneType

        # Each risk engine belongs to exactly one camera, so its zone manager
        # can be rebuilt safely whenever that camera's metadata changes.
        risk_engine.zone_manager.clear()

        for index, zone_data in enumerate(zones):
            if not isinstance(zone_data, dict):
                continue
            bounds = zone_data.get("bounds") if isinstance(zone_data, dict) else None
            if not isinstance(bounds, list) or len(bounds) != 4:
                continue
            zone_type_name = str(zone_data.get("type", "RESTRICTED")).upper()
            zone_type = ZoneType.__members__.get(zone_type_name, ZoneType.RESTRICTED)
            risk_engine.zone_manager.add_zone(
                Zone(
                    zone_id=f"{camera_id}_zone_{index}",
                    name=str(zone_data.get("name", zone_type.value.title())),
                    zone_type=zone_type,
                    bounds=tuple(int(value) for value in bounds),
                    description=str(zone_data.get("description", "")),
                )
            )
        self._configured_zones[camera_id] = fingerprint
        logger.info("Configured %s risk zones for camera %s", risk_engine.zone_manager.zone_count, camera_id)

    def _behavior_labels(self, behavior: Any) -> List[str]:
        if behavior is None:
            return ["normal"]
        labels = [item.name.lower() for item in behavior.active_behaviors]
        return labels or ["normal"]

    def _movement_state(self, motion: Any) -> str:
        if motion is None:
            return "tracked"
        if motion.speed_smoothed >= 15.0:
            return "running"
        if motion.is_moving:
            return "moving"
        return "stationary"

    def _motion_behavior_confirmed(self, analysis: Any) -> bool:
        if analysis is None:
            return False
        motion = analysis.motion
        bbox = analysis.current_bbox
        width = max(float(bbox[2] - bbox[0]), 1.0)
        height = max(float(bbox[3] - bbox[1]), 1.0)
        bbox_scale = max(width, height)
        distance_ratio = motion.distance_traveled / bbox_scale

        return (
            analysis.history_length >= 12
            and analysis.time_tracked >= 0.35
            and motion.speed_smoothed >= 18.0
            and distance_ratio >= 0.6
        )

    def _risk_level_from_score(self, score: float) -> str:
        if score >= 0.75:
            return "CRITICAL"
        if score >= 0.50:
            return "HIGH"
        if score >= 0.25:
            return "MEDIUM"
        return "LOW"

    def _candidate_level_from_score(self, score: float) -> str:
        return "CANDIDATE_MEDIUM" if score >= 0.25 else "LOW"

    def _build_evidence(
        self,
        track: Any,
        bbox: Tuple[int, int, int, int],
        risk_level: str,
        risk_score: float,
        behavior_labels: List[str],
        raw_behavior_labels: List[str],
        factors: List[str],
        explanation: str,
        motion_confirmed: bool,
        frame_detected_classes: List[str],
        association: Optional[Dict[str, Any]] = None,
        threat_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        capabilities = self.get_model_capabilities()
        class_name = getattr(track, "class_name", "unknown")
        is_person = getattr(track, "is_person", False) or getattr(track, "class_id", None) == 0
        is_weapon = bool(getattr(track, "is_weapon", False))
        is_vehicle = bool(getattr(track, "is_vehicle", False)) or str(getattr(track, "object_category", "")).lower() == "vehicle"
        confidence = float(getattr(track, "confidence", 0.0))
        motion_signal = any(label in {"running", "erratic_motion", "direction_reversal"} for label in raw_behavior_labels)
        reason_codes = set(self._reason_code(factor) for factor in factors)
        evidence_type = "object_detection"
        verification_status = "confirmed"
        association = association or None
        association_type = association.get("association_type") if association else None
        association_score = float(association.get("association_score") or 0.0) if association else None
        stable_frames = int(association.get("stable_frames") or 0) if association else 0
        weapon_class = None
        weapon_confidence = None
        person_track_id = None
        weapon_track_id = None
        nearby_person_track_id = None
        threat_event_type = None
        evidence_objects: List[Dict[str, Any]] = []

        if is_person or is_vehicle:
            if is_person:
                reason_codes.add("PERSON_DETECTED")
            if is_vehicle:
                reason_codes.add("VEHICLE_DETECTED")
            explanation = self._evidence_explainer.explain_track(
                class_name=class_name,
                confidence=confidence,
                is_person=is_person,
                is_vehicle=is_vehicle,
                is_weapon=False,
                association=association,
                verification_status="confirmed",
                risk_level="LOW",
            )
            risk_level = "LOW"
            risk_score = min(risk_score, 0.10)

        if is_weapon:
            weapon_class = str(class_name).lower()
            weapon_confidence = confidence
            weapon_track_id = association.get("weapon_track_id") if association else str(getattr(track, "track_id", ""))
            person_track_id = association.get("person_track_id") if association else None
            evidence_type = "object_detection"
            reason_codes.add("WEAPON_MODEL_DETECTION")
            reason_codes.add("WEAPON_LIKE_OBJECT_DETECTION")
            reason_codes.add(f"{weapon_class.upper()}_DETECTED")
            if not capabilities["weapon_detection_supported"]:
                reason_codes.add("WEAPON_MODEL_UNSUPPORTED")
                risk_level = "LOW"
                risk_score = min(risk_score, 0.10)
                evidence_type = "unsupported"
                verification_status = "unsupported"
                explanation = "No weapon model is currently enabled. Risk remains LOW because no confirmed threat evidence exists."
            elif confidence < 0.50:
                risk_level = "CANDIDATE_MEDIUM"
                risk_score = max(min(risk_score, 0.30), 0.25)
                verification_status = "needs_verification"
                reason_codes.add("LOW_CONFIDENCE_WEAPON_CANDIDATE")
            elif not association:
                risk_level = "MEDIUM"
                risk_score = max(min(risk_score, 0.49), 0.40)
                verification_status = "candidate"
                reason_codes.add("WEAPON_DETECTED_WITHOUT_PERSON_ASSOCIATION")
            elif association_type == "near":
                evidence_type = "proximity"
                reason_codes.add("WEAPON_NEAR_PERSON")
                if confidence >= 0.70 and stable_frames >= 2:
                    risk_level = "HIGH"
                    risk_score = max(min(0.70, confidence * 0.65 + (association_score or 0.0) * 0.25), 0.55)
                    verification_status = "confirmed"
                    reason_codes.add("WEAPON_NEAR_PERSON_STABLE")
                else:
                    risk_level = "MEDIUM"
                    risk_score = max(min(risk_score, 0.49), 0.42)
                    verification_status = "candidate"
                    reason_codes.add("TEMPORAL_CONFIRMATION_REQUIRED")
            elif association_type in {"contained", "overlap"}:
                evidence_type = "proximity"
                reason_codes.add("WEAPON_ASSOCIATED_WITH_PERSON")
                if confidence >= 0.85 and (association_score or 0.0) >= 0.75 and stable_frames >= 3:
                    # Bounding-box containment is useful evidence, but it is
                    # not proof of harmful intent, ownership, or an active
                    # confrontation. Keep it HIGH and require a separate
                    # interaction/explicit-critical signal for CRITICAL.
                    risk_level = "HIGH"
                    risk_score = max(min(0.72, confidence * 0.60 + (association_score or 0.0) * 0.25), 0.60)
                    verification_status = "confirmed"
                    reason_codes.add("STABLE_WEAPON_PERSON_ASSOCIATION")
                    reason_codes.add("INTERACTION_CONFIRMATION_REQUIRED")
                elif confidence >= 0.70 and stable_frames >= 2:
                    risk_level = "HIGH"
                    risk_score = max(min(0.72, confidence * 0.60 + (association_score or 0.0) * 0.25), 0.55)
                    verification_status = "confirmed"
                    reason_codes.add("WEAPON_PERSON_ASSOCIATION_PENDING_CRITICAL_CONFIRMATION")
                else:
                    risk_level = "MEDIUM"
                    risk_score = max(min(risk_score, 0.49), 0.45)
                    verification_status = "candidate"
                    reason_codes.add("TEMPORAL_CONFIRMATION_REQUIRED")

            explanation = self._evidence_explainer.explain_track(
                class_name=class_name,
                confidence=confidence,
                is_weapon=True,
                association=association,
                verification_status=verification_status,
                risk_level=risk_level,
            )

        elif association and is_person:
            weapon_class = str(association.get("weapon_class") or "weapon").lower()
            weapon_confidence = float(association.get("weapon_confidence") or 0.0)
            weapon_track_id = association.get("weapon_track_id")
            person_track_id = association.get("person_track_id")
            evidence_type = "proximity"
            reason_codes.add("PERSON_ASSOCIATED_WITH_WEAPON_EVIDENCE")
            if association_type == "near" and weapon_confidence >= 0.70 and stable_frames >= 2:
                risk_level = "HIGH"
                risk_score = max(risk_score, 0.55)
                verification_status = "confirmed"
                reason_codes.add("WEAPON_NEAR_PERSON_STABLE")
            elif association_type in {"contained", "overlap"} and weapon_confidence >= 0.85 and (association_score or 0.0) >= 0.75 and stable_frames >= 3:
                risk_level = "HIGH"
                risk_score = max(risk_score, 0.60)
                verification_status = "confirmed"
                reason_codes.add("STABLE_WEAPON_PERSON_ASSOCIATION")
                reason_codes.add("INTERACTION_CONFIRMATION_REQUIRED")
            elif association_type in {"contained", "overlap", "near"}:
                risk_level = "MEDIUM"
                risk_score = max(risk_score, 0.42)
                verification_status = "candidate"
                reason_codes.add("TEMPORAL_CONFIRMATION_REQUIRED")
            explanation = self._evidence_explainer.explain_track(
                class_name=weapon_class,
                confidence=weapon_confidence,
                is_weapon=True,
                association=association,
                verification_status=verification_status,
                risk_level=risk_level,
            )

        if motion_signal:
            reason_codes.add("BBOX_MOTION_CANDIDATE")
            reason_codes.add("TEMPORAL_CONFIRMATION_REQUIRED")
            if not (is_weapon or association) and risk_level not in {"HIGH", "CRITICAL"}:
                evidence_type = "temporal_behavior" if motion_confirmed else "bbox_motion"
                verification_status = "candidate"
                risk_level = "CANDIDATE_MEDIUM"
                risk_score = min(max(risk_score, 0.25), 0.35)
                explanation = "Motion candidate detected from bounding-box movement. Candidate movement requires further temporal confirmation."

        if "loitering" in behavior_labels:
            reason_codes.add("LOITERING_CANDIDATE")
            if not (is_weapon or association) and risk_level not in {"HIGH", "CRITICAL"}:
                evidence_type = "temporal_behavior"
                verification_status = "candidate"
                risk_level = "CANDIDATE_MEDIUM"
                risk_score = min(max(risk_score, 0.25), 0.45)
                explanation = "Candidate movement requires further temporal confirmation."

        if threat_context:
            context_level = str(threat_context.get("risk_level") or "LOW").upper()
            context_score = float(threat_context.get("risk_score") or 0.0)
            context_status = str(threat_context.get("verification_status") or "candidate")
            level_rank = {"LOW": 0, "CANDIDATE_MEDIUM": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
            reason_codes.update(str(code) for code in threat_context.get("reason_codes") or [])
            threat_event_type = str(threat_context.get("event_type") or "possible_threat")
            person_track_id = str(threat_context.get("armed_person_track_id") or person_track_id or "") or None
            nearby_person_track_id = str(threat_context.get("nearby_person_track_id") or "") or None
            weapon_track_id = str(threat_context.get("weapon_track_id") or weapon_track_id or "") or None
            weapon_class = threat_context.get("weapon_class") or weapon_class
            if threat_context.get("weapon_confidence") is not None:
                weapon_confidence = float(threat_context["weapon_confidence"])
            association_type = threat_context.get("association_type") or association_type
            if threat_context.get("association_score") is not None:
                association_score = float(threat_context["association_score"])
            stable_frames = max(stable_frames, int(threat_context.get("confirmed_frames") or 0))
            if level_rank.get(context_level, 0) >= level_rank.get(risk_level, 0):
                risk_level = context_level
                risk_score = max(risk_score, context_score)
                verification_status = context_status
            evidence_type = (
                "weapon_aggression_context"
                if threat_context.get("weapon_track_id")
                else "aggression_context"
            )
            explanation = str(threat_context.get("explanation") or explanation)

        evidence_weapon_class = str(weapon_class or (association or {}).get("weapon_class") or "").strip()
        if (is_weapon or evidence_weapon_class) and not self._weapon_class_supported(capabilities, evidence_weapon_class or class_name):
            reason_codes.update({"WEAPON_MODEL_UNSUPPORTED", "WEAPON_CLASS_UNSUPPORTED"})
            risk_level = "LOW"
            risk_score = min(risk_score, 0.10)
            evidence_type = "unsupported"
            verification_status = "unsupported"
            if capabilities.get("weapon_detection_supported"):
                explanation = (
                    f"{(evidence_weapon_class or str(class_name)).title()} is not supported by the available detector weights. "
                    "Operator review requires a compatible local weapon model."
                )
            else:
                explanation = "No weapon model is currently enabled. Risk remains LOW because no confirmed threat evidence exists."

        weaponish_text = " ".join([explanation, *factors, *reason_codes]).lower()
        if any(term in weaponish_text for term in ("weapon", "knife", "gun", "firearm", "pistol", "rifle")):
            if not capabilities["weapon_detection_supported"]:
                reason_codes.add("WEAPON_MODEL_UNSUPPORTED")
                explanation = "No weapon model is currently enabled. Risk remains LOW because no confirmed threat evidence exists."
                risk_level = "LOW"
                risk_score = min(risk_score, 0.10)
                evidence_type = "unsupported"
                verification_status = "unsupported"

        if verification_status != "unsupported" and "ZONE_INTRUSION" in reason_codes:
            evidence_type = "zone_intrusion"
            verification_status = "confirmed"

        if risk_level in {"HIGH", "CRITICAL"}:
            has_confirmed_high_evidence = any(
                code in reason_codes
                for code in {
                    "ZONE_INTRUSION",
                    "CONFIRMED_MULTI_SIGNAL_RISK",
                    "WEAPON_NEAR_PERSON_STABLE",
                    "STABLE_WEAPON_PERSON_ASSOCIATION",
                    "POSSIBLE_ARMED_THREAT",
                    "CONFIRMED_AGGRESSION_PATTERN",
                    "CRITICAL_WEAPON_AGGRESSION_COMBINATION",
                    "HIGH_CONFIDENCE_WEAPON_ASSOCIATION",
                }
            )
            if not has_confirmed_high_evidence:
                reason_codes.add("HIGH_RISK_NOT_CONFIRMED")
                risk_level = "CANDIDATE_MEDIUM" if risk_score >= 0.25 else "LOW"
                risk_score = min(risk_score, 0.35)
                verification_status = "candidate" if risk_level == "CANDIDATE_MEDIUM" else verification_status
                explanation = "Risk remains LOW because no confirmed threat evidence exists." if risk_level == "LOW" else "Motion candidate detected from bounding-box movement. Candidate movement requires further temporal confirmation."

        if risk_level == "CRITICAL":
            has_critical_evidence = any(
                code in reason_codes
                for code in {
                    "EXPLICIT_CRITICAL_SIGNAL",
                    "CRITICAL_WEAPON_AGGRESSION_COMBINATION",
                }
            )
            if not has_critical_evidence:
                reason_codes.add("CRITICAL_EVIDENCE_MISSING")
                risk_level = "CANDIDATE_MEDIUM"
                risk_score = min(risk_score, 0.35)
                verification_status = "candidate"
                explanation = "Candidate movement requires further temporal confirmation."

        detector_source = getattr(track, "model_source", "") or capabilities["model_name"] or "yolo"
        model_source = [detector_source, "bytetrack"]
        if association:
            model_source.append("person_weapon_association")
        if threat_context:
            model_source.append("weapon_aggression_rules")
        if evidence_type in {"bbox_motion", "temporal_behavior"}:
            model_source.append("bbox_motion_rules")
        if is_weapon or association:
            weapon_model_source = (
                (threat_context or {}).get("weapon_model_source")
                or (association or {}).get("weapon_model_source")
                or detector_source
            )
            evidence_objects.append({
                "object_class": weapon_class or str(class_name).lower(),
                "confidence": weapon_confidence if weapon_confidence is not None else confidence,
                "track_id": weapon_track_id or str(getattr(track, "track_id", "")),
                "bbox": association.get("weapon_bbox") if association else list(bbox),
                "model_source": weapon_model_source,
            })
        if association and person_track_id:
            evidence_objects.append({
                "object_class": "person",
                "confidence": association.get("person_confidence"),
                "track_id": person_track_id,
                "bbox": association.get("person_bbox"),
                "model_source": "bytetrack",
            })
        elif threat_context and person_track_id:
            evidence_objects.append({
                "object_class": "person",
                "confidence": confidence,
                "track_id": person_track_id,
                "bbox": threat_context.get("armed_person_bbox") or list(bbox),
                "model_source": "bytetrack",
                "role": "observed_person",
            })
        if threat_context and nearby_person_track_id:
            evidence_objects.append({
                "object_class": "person",
                "confidence": None,
                "track_id": nearby_person_track_id,
                "bbox": threat_context.get("nearby_person_bbox"),
                "model_source": "bytetrack",
                "role": "nearby_person",
            })

        return {
            "risk_level": risk_level,
            "risk_score": round(float(risk_score), 3),
            "evidence_type": evidence_type,
            "confidence": confidence,
            "model_source": model_source,
            "verification_status": verification_status,
            "reason_codes": sorted(code for code in reason_codes if code),
            "visual_evidence": {
                "bbox": list(bbox),
                "detected_class": class_name,
                "detected_classes_in_frame": frame_detected_classes,
                "object_confidence": confidence,
                "weapon_detection_supported": capabilities["weapon_detection_supported"],
                "weapon_class_supported": self._weapon_class_supported(capabilities, evidence_weapon_class or class_name),
                "action_recognition_supported": capabilities["action_recognition_supported"],
                "pose_estimation_supported": capabilities["pose_estimation_supported"],
                "semantic_verification_supported": capabilities["semantic_verification_supported"],
                "association": association,
                "threat_context": threat_context,
            },
            "weapon_class": weapon_class,
            "weapon_confidence": round(weapon_confidence, 3) if weapon_confidence is not None else None,
            "person_track_id": person_track_id,
            "weapon_track_id": weapon_track_id,
            "association_type": association_type,
            "association_score": round(association_score, 3) if association_score is not None else None,
            "stable_frames": stable_frames,
            "evidence_objects": evidence_objects,
            "threat_event_type": threat_event_type,
            "nearby_person_track_id": nearby_person_track_id,
            "threat_context": threat_context,
            "explanation": self._sanitize_explanation(explanation, capabilities),
        }

    def _reason_code(self, value: str) -> str:
        normalized = "".join(ch if ch.isalnum() else "_" for ch in str(value).upper()).strip("_")
        aliases = {
            "PERSON_DETECTED": "PERSON_DETECTED",
            "MULTIPLE_PERSONS": "MULTIPLE_PERSONS",
            "CROWD_DENSITY": "CROWD_DENSITY",
            "RUNNING": "BBOX_MOTION_CANDIDATE",
            "ERRATIC_MOVEMENT": "BBOX_MOTION_CANDIDATE",
            "DIRECTION_REVERSAL": "BBOX_MOTION_CANDIDATE",
            "LOITERING": "LOITERING_CANDIDATE",
            "WEAPON_OVERLAP": "WEAPON_NEAR_PERSON",
            "WEAPON_PROXIMITY": "WEAPON_NEAR_PERSON",
            "WEAPON_LIKE_OBJECT_PROXIMITY": "WEAPON_NEAR_PERSON",
            "WEAPON_DETECTED": "WEAPON_DETECTED",
            "ZONE_INTRUSION": "ZONE_INTRUSION",
        }
        if normalized.startswith("WEAPON_OVERLAP") or normalized.startswith("WEAPON_PROXIMITY"):
            return "WEAPON_NEAR_PERSON"
        return aliases.get(normalized, normalized)

    @staticmethod
    def _weapon_class_supported(capabilities: Dict[str, Any], class_name: str) -> bool:
        if not capabilities.get("weapon_detection_supported"):
            return False
        configured = capabilities.get("supported_weapon_classes") or capabilities.get("supported_classes") or []
        supported = {str(value).strip().lower().replace("_", " ") for value in configured}
        normalized = str(class_name or "").strip().lower().replace("_", " ")
        aliases = {
            "gun": {"gun", "pistol", "firearm"},
            "pistol": {"gun", "pistol", "firearm"},
            "firearm": {"gun", "pistol", "firearm"},
            "bat": {"bat", "baseball bat"},
            "baseball bat": {"bat", "baseball bat"},
        }
        return bool((aliases.get(normalized, {normalized})) & supported)

    def _sanitize_explanation(self, explanation: str, capabilities: Dict[str, Any]) -> str:
        lowered = explanation.lower()
        forbidden_without_weapon = ("weapon", "knife", "gun", "firearm", "pistol", "rifle")
        forbidden_actions = ("fighting", "fight", "falling", "fall", "attack", "critical threat")
        if not capabilities["weapon_detection_supported"] and any(term in lowered for term in forbidden_without_weapon):
            return "No weapon model is currently enabled. Risk remains LOW because no confirmed threat evidence exists."
        if not capabilities["action_recognition_supported"] and any(term in lowered for term in forbidden_actions):
            return "Risk remains LOW because no confirmed threat evidence exists."
        return explanation

    def _apply_frame_rules(
        self,
        track: Any,
        analysis: Any,
        base_score: float,
        base_level: str,
        base_explanation: str,
        factors: List[str],
        behavior_labels: List[str],
        crowd_metrics: Any,
        proximity: Any,
    ) -> Tuple[float, str, str, List[str]]:
        score = base_score
        explanation_parts = [base_explanation]
        factor_set = set(factors)

        if getattr(track, "is_person", False) or getattr(track, "class_id", None) == 0:
            if crowd_metrics.person_count == 1 and score < 0.25:
                score = max(score, 0.05)
                factor_set.add("person_detected")
                explanation_parts.append("Person detected.")
            if crowd_metrics.person_count >= 3:
                score = max(score, 0.25)
                factor_set.add("multiple_persons")
                explanation_parts.append(f"{crowd_metrics.person_count} persons tracked in frame")
            if crowd_metrics.crowd_detected:
                score = max(score, 0.45)
                factor_set.add("crowd_density")
                explanation_parts.append(f"crowd density threshold reached; max cell density {crowd_metrics.max_density}")

        motion_confirmed = self._motion_behavior_confirmed(analysis)

        if ("running" in behavior_labels or "erratic_motion" in behavior_labels) and motion_confirmed:
            score = max(score, 0.35)
            factor_set.add("bbox_motion_candidate")
            explanation_parts.append("Motion candidate detected from bounding-box movement.")
        if "loitering" in behavior_labels:
            score = max(score, 0.35)
            factor_set.add("loitering")
            explanation_parts.append("Candidate movement requires further temporal confirmation.")

        proximity_triggers = list(getattr(proximity, "triggers", []))
        if self.get_model_capabilities()["weapon_detection_supported"] and proximity_triggers and (getattr(track, "is_person", False) or getattr(track, "is_weapon", False)):
            score = max(score, float(getattr(proximity, "risk_score", 0.0)))
            factor_set.update(proximity_triggers)
            explanation_parts.append("person and weapon-like object proximity detected")
            if any(trigger.startswith("weapon_overlap") for trigger in proximity_triggers):
                score = max(score, 0.90)
                explanation_parts.append("weapon-like object overlaps or is contained by person bounding box")

        level = self._candidate_level_from_score(score)
        return score, level if score >= base_score else base_level, "; ".join(dict.fromkeys(explanation_parts)), sorted(factor_set)

    def _registry_entry(self, track_id: str) -> Optional[Dict[str, Any]]:
        for entry in get_state().get_object_registry():
            if str(entry.get("track_id")) == str(track_id):
                return entry
        return None

    @staticmethod
    def _is_primary_threat_track(track_payload: Dict[str, Any]) -> bool:
        threat_context = track_payload.get("threat_context") or {}
        if not threat_context:
            return True
        actor_id = str(
            threat_context.get("armed_person_track_id")
            or track_payload.get("person_track_id")
            or ""
        )
        return str(track_payload.get("raw_track_id") or "") == actor_id

    @staticmethod
    def _camera_track_key(camera_id: str, raw_track_id: object) -> Optional[str]:
        value = str(raw_track_id or "").strip()
        if not value:
            return None
        return value if value.startswith(f"{camera_id}:") else f"{camera_id}:{value}"

    def _persist_frame_observations(
        self,
        *,
        camera_id: str,
        source_epoch: str,
        frame_id: int,
        captured_at: datetime,
        track_payloads: List[Dict[str, Any]],
    ) -> None:
        """Persist raw camera measurements before event or alert policy runs.

        The first local-PC slice stores one detector/track observation per
        current track and one relation observation for a reported geometric
        association. It never turns detection confidence into incident risk.
        """
        if not track_payloads:
            return
        try:
            from aegis.database.connection import get_db_session
            from aegis.database.persistence import get_persistence_status
            from aegis.database.repositories import ObservationRepository

            with get_db_session() as session:
                repository = ObservationRepository(session)
                for payload in track_payloads:
                    track_key = str(payload.get("track_id") or "").strip() or None
                    raw_track_id = str(payload.get("raw_track_id") or track_key or "untracked")
                    base_id = f"obs:{camera_id}:{source_epoch}:{frame_id}:{raw_track_id}"
                    metadata = {
                        "risk_level": payload.get("risk_level"),
                        "policy_score": float(payload.get("risk_score") or 0.0),
                        "verification_status": payload.get("verification_status"),
                        "reason_codes": list(payload.get("reason_codes") or []),
                        "risk_factors": list(payload.get("risk_factors") or []),
                        "model_source": list(payload.get("model_source") or []),
                        "behavior_labels": list(payload.get("behavior_labels") or []),
                        "stable_frames": payload.get("stable_frames"),
                    }
                    observation, _ = repository.create_or_get(
                        observation_id=f"{base_id}:detection",
                        camera_id=camera_id,
                        source_epoch=source_epoch,
                        captured_at=captured_at,
                        frame_id=frame_id,
                        track_key=track_key,
                        related_track_key=None,
                        observation_type="track_detection",
                        label=str(payload.get("class_name") or "unknown"),
                        model_confidence=float(payload.get("confidence") or 0.0),
                        bounding_box=payload.get("bbox"),
                        zone_id=payload.get("zone_id"),
                        zone_name=payload.get("zone_name"),
                        metadata=metadata,
                    )
                    observation_ids = [observation.observation_id]
                    association_type = str(payload.get("association_type") or "none")
                    related_raw_id = (
                        payload.get("weapon_track_id")
                        if payload.get("is_person")
                        else payload.get("person_track_id")
                    )
                    related_track_key = self._camera_track_key(camera_id, related_raw_id)
                    if association_type in {"near", "overlap", "contained"} and related_track_key:
                        relation, _ = repository.create_or_get(
                            observation_id=f"{base_id}:association:{related_track_key}",
                            camera_id=camera_id,
                            source_epoch=source_epoch,
                            captured_at=captured_at,
                            frame_id=frame_id,
                            track_key=track_key,
                            related_track_key=related_track_key,
                            observation_type="object_person_association",
                            label=association_type,
                            model_confidence=payload.get("association_score"),
                            bounding_box=payload.get("bbox"),
                            zone_id=payload.get("zone_id"),
                            zone_name=payload.get("zone_name"),
                            metadata={
                                **metadata,
                                "association_type": association_type,
                                "association_score": payload.get("association_score"),
                                "weapon_class": payload.get("weapon_class"),
                            },
                        )
                        observation_ids.append(relation.observation_id)
                    payload["observation_ids"] = observation_ids
                    payload["observation_persistence_status"] = "persisted"
            get_persistence_status().record_success("camera_observations")
        except Exception as exc:
            for payload in track_payloads:
                payload["observation_ids"] = []
                payload["observation_persistence_status"] = "failed"
            try:
                from aegis.database.persistence import get_persistence_status

                get_persistence_status().record_failure("camera_observations", exc)
            except Exception:
                pass
            logger.warning("Observation persistence failed camera_id=%s: %s", camera_id, exc)

    def _maybe_generate_detection_event(
        self,
        camera_id: str,
        track_payload: Dict[str, Any],
        frame_number: int,
        timestamp: datetime,
    ) -> Optional[Dict[str, Any]]:
        event_type = self._detection_event_type(track_payload)
        verification_status = str(track_payload.get("verification_status") or "confirmed")
        association_type = str(track_payload.get("association_type") or "none")
        risk_level = str(track_payload.get("risk_level") or "LOW")
        if track_payload.get("threat_event_type"):
            event_key = f"{self._alert_confirmation_key(camera_id, track_payload)}:{verification_status}:{association_type}:{risk_level}"
        else:
            event_key = f"{camera_id}:{track_payload.get('track_id')}:{event_type}:{verification_status}:{association_type}:{risk_level}"
        if event_key in self._emitted_detection_events:
            return None
        self._emitted_detection_events.add(event_key)

        confidence = float(track_payload.get("confidence") or 0.0)
        is_weapon = bool(track_payload.get("is_weapon"))
        if is_weapon and "risk_level" not in track_payload:
            risk_level = "CANDIDATE_MEDIUM" if confidence < 0.70 else "MEDIUM"
            verification_status = "candidate"
            track_payload["risk_level"] = risk_level
            track_payload["risk_score"] = 0.35 if confidence < 0.70 else 0.45
            track_payload["verification_status"] = verification_status
            track_payload["reason_codes"] = [
                "WEAPON_MODEL_DETECTION",
                "LOW_CONFIDENCE_WEAPON_CANDIDATE" if confidence < 0.70 else "WEAPON_DETECTED_WITHOUT_PERSON_ASSOCIATION",
            ]
        severity = "warning" if risk_level in {"CANDIDATE_MEDIUM", "MEDIUM", "HIGH", "CRITICAL"} else "info"
        reason_codes = ["REAL_OBJECT_DETECTION", event_type.upper(), *list(track_payload.get("reason_codes") or [])]

        if is_weapon:
            reason_codes.append("WEAPON_MODEL_DETECTION")
        elif track_payload.get("is_vehicle"):
            reason_codes.append("VEHICLE_DETECTION")
        elif track_payload.get("is_person"):
            reason_codes.append("PERSON_DETECTION")

        event_id = f"det-{camera_id}-{frame_number}-{uuid.uuid4().hex[:8]}"
        class_name = str(track_payload.get("class_name", "unknown"))
        explanation = str(track_payload.get("risk_explanation") or f"{class_name} detected by backend object detector.")
        if risk_level == "CRITICAL":
            event_type = "weapon_association_confirmed"
        elif track_payload.get("association_type") in {"contained", "overlap", "near"}:
            event_type = "weapon_person_association"

        event_payload = {
            "id": event_id,
            "event_id": event_id,
            "evidence_id": event_id,
            "incident_id": None,
            "event_type": event_type,
            "camera_id": camera_id,
            "track_id": track_payload.get("track_id"),
            "timestamp": timestamp.isoformat(),
            "severity": severity,
            "risk_level": risk_level,
            "risk_score": float(track_payload.get("risk_score") or 0.0),
            "class_name": class_name,
            "object_class": class_name,
            "object_type": class_name,
            "confidence": confidence,
            "bbox": track_payload.get("bbox"),
            "model_source": track_payload.get("model_source") or [track_payload.get("detection_model_source") or "unknown"],
            "verification_status": verification_status,
            "evidence_type": track_payload.get("evidence_type"),
            "reason_codes": sorted(set(reason_codes)),
            "visual_evidence": track_payload.get("visual_evidence") or {
                "bbox": track_payload.get("bbox"),
                "detected_class": class_name,
                "object_confidence": confidence,
                "model_source": track_payload.get("detection_model_source"),
            },
            "weapon_class": track_payload.get("weapon_class"),
            "weapon_confidence": track_payload.get("weapon_confidence"),
            "person_track_id": track_payload.get("person_track_id"),
            "weapon_track_id": track_payload.get("weapon_track_id"),
            "association_type": track_payload.get("association_type"),
            "association_score": track_payload.get("association_score"),
            "stable_frames": track_payload.get("stable_frames"),
            "evidence_objects": track_payload.get("evidence_objects", []),
            "threat_event_type": track_payload.get("threat_event_type"),
            "nearby_person_track_id": track_payload.get("nearby_person_track_id"),
            "threat_context": track_payload.get("threat_context"),
            "detected_objects": [class_name],
            "detected_classes": [class_name],
            "behavior_labels": [],
            "frame_number": frame_number,
            "frame_id": frame_number,
            "title": event_type,
            "description": explanation,
            "explanation": explanation,
            "reason": explanation,
            "snapshot_path": None,
        }
        self._events.append(event_payload)
        get_state().add_event(event_payload)
        return event_payload

    def _detection_event_type(self, track_payload: Dict[str, Any]) -> str:
        if track_payload.get("threat_event_type"):
            return str(track_payload["threat_event_type"])
        if track_payload.get("is_weapon"):
            return "weapon_detected"
        if track_payload.get("is_vehicle"):
            return "vehicle_detected"
        if track_payload.get("is_person"):
            return "person_detected"
        return "object_detected"

    def _maybe_generate_alert(
        self,
        camera_id: str,
        track_payload: Dict[str, Any],
        frame_number: int,
        timestamp: datetime,
        frame: np.ndarray,
    ) -> Optional[Dict[str, Any]]:
        risk_level = track_payload["risk_level"]
        risk_score = float(track_payload["risk_score"])
        track_key = str(track_payload["track_id"])
        confirmation_key = self._alert_confirmation_key(camera_id, track_payload)

        verification_status = str(track_payload.get("verification_status", "needs_verification"))
        reason_codes = set(track_payload.get("reason_codes") or [])
        critical_reason_codes = {
            "EXPLICIT_CRITICAL_SIGNAL",
            "CRITICAL_WEAPON_AGGRESSION_COMBINATION",
        }
        high_reason_codes = critical_reason_codes | {"ZONE_INTRUSION", "CONFIRMED_MULTI_SIGNAL_RISK"}
        high_reason_codes.update({
            "WEAPON_NEAR_PERSON_STABLE",
            "STABLE_WEAPON_PERSON_ASSOCIATION",
            "POSSIBLE_ARMED_THREAT",
            "CONFIRMED_AGGRESSION_PATTERN",
            "HIGH_CONFIDENCE_WEAPON_ASSOCIATION",
        })

        if verification_status not in {"confirmed", "critical"}:
            self._high_risk_frames[confirmation_key] = 0
            return None
        if risk_level not in {"HIGH", "CRITICAL"}:
            self._high_risk_frames[confirmation_key] = 0
            return None
        if risk_level == "HIGH" and not (reason_codes & high_reason_codes):
            self._high_risk_frames[confirmation_key] = 0
            return None
        if risk_level == "CRITICAL" and not (reason_codes & critical_reason_codes):
            self._high_risk_frames[confirmation_key] = 0
            return None

        self._high_risk_frames[confirmation_key] = self._high_risk_frames.get(confirmation_key, 0) + 1
        threat_context = track_payload.get("threat_context") or {}
        required_frames = 1 if threat_context and verification_status in {"confirmed", "critical"} else 3
        if self._high_risk_frames[confirmation_key] < required_frames:
            return None

        alert_manager = self._get_alert_manager()
        alert = None
        if alert_manager:
            alert = alert_manager.process_risk(
                track_id=track_key,
                risk_level=risk_level,
                risk_score=risk_score,
                message=track_payload["risk_explanation"],
                zone=camera_id,
                factors=track_payload["risk_factors"],
                cooldown_key=confirmation_key,
            )
            if alert is None:
                return None
        else:
            current_time = time.monotonic()
            last_alert_time = self._fallback_alert_cooldowns.get(confirmation_key)
            if last_alert_time is not None and current_time - last_alert_time < 30.0:
                return None
            self._fallback_alert_cooldowns[confirmation_key] = current_time

        event_id = alert.event_id if alert else f"{camera_id}-{frame_number}-{uuid.uuid4().hex[:8]}"
        snapshot = self._save_event_snapshot(
            camera_id=camera_id,
            event_id=event_id,
            timestamp=timestamp,
            frame=frame,
        )
        related_track_ids: List[str] = []
        for related_track_id in (
            track_payload.get("weapon_track_id"),
            track_payload.get("nearby_person_track_id"),
        ):
            if related_track_id is None:
                continue
            related_key = f"{camera_id}:{related_track_id}"
            if related_key != track_key and related_key not in related_track_ids:
                related_track_ids.append(related_key)
        event_payload = {
            "id": event_id,
            "event_id": event_id,
            "evidence_id": None,
            "observation_ids": list(track_payload.get("observation_ids") or []),
            "observation_persistence_status": track_payload.get("observation_persistence_status"),
            "evidence_status": "pending",
            "incident_id": None,
            # AlertManager exposes one externally assigned alert/event ID.
            # Retain it in both fields so API consumers can trace either
            # identifier without inventing a second identity scheme.
            "alert_id": alert.event_id if alert else None,
            # This marker makes the operational context distinguish confirmed
            # risk alerts from ordinary detection events without changing risk
            # scoring or alert-trigger behaviour.
            "type": "risk_alert",
            "event_type": "risk_alert",
            "camera_id": camera_id,
            "camera_name": track_payload.get("camera_name"),
            "track_id": track_key,
            "timestamp": timestamp.isoformat(),
            "severity": risk_level,
            "risk_level": risk_level,
            "risk_score": risk_score,
            "confidence": track_payload.get("confidence"),
            "object_class": track_payload["class_name"],
            "bbox": track_payload.get("bbox"),
            "detected_objects": track_payload["detected_classes"],
            "detected_classes": track_payload["detected_classes"],
            "behavior_labels": track_payload["behavior_labels"],
            "evidence_type": track_payload.get("evidence_type"),
            "model_source": track_payload.get("model_source", []),
            "verification_status": verification_status,
            "reason_codes": track_payload.get("reason_codes", []),
            "visual_evidence": track_payload.get("visual_evidence", {}),
            "weapon_class": track_payload.get("weapon_class"),
            "weapon_confidence": track_payload.get("weapon_confidence"),
            "person_track_id": track_payload.get("person_track_id"),
            "weapon_track_id": track_payload.get("weapon_track_id"),
            "association_type": track_payload.get("association_type"),
            "association_score": track_payload.get("association_score"),
            "stable_frames": track_payload.get("stable_frames"),
            "evidence_objects": track_payload.get("evidence_objects", []),
            "threat_event_type": track_payload.get("threat_event_type"),
            "nearby_person_track_id": track_payload.get("nearby_person_track_id"),
            "related_track_ids": related_track_ids,
            "threat_context": track_payload.get("threat_context"),
            "explanation": track_payload["risk_explanation"],
            "description": track_payload["risk_explanation"],
            "reason": track_payload["risk_explanation"],
            "factors": track_payload["risk_factors"],
            "triggers": track_payload["risk_factors"],
            "object_type": track_payload["class_name"],
            "class_name": track_payload["class_name"],
            "frame_number": frame_number,
            "frame_id": frame_number,
            "snapshot_path": snapshot.path,
            "snapshot_status": snapshot.status,
            "clip_path": None,
            "confirmed_frames": max(
                self._high_risk_frames[confirmation_key],
                int(threat_context.get("confirmed_frames") or 0),
            ),
            "title": self._alert_title(track_payload, risk_level),
            "zone": track_payload.get("zone_name") or camera_id,
            "zone_id": track_payload.get("zone_id"),
            "zone_name": track_payload.get("zone_name"),
        }
        persisted = self._persist_event(event_payload)
        if persisted:
            event_payload["evidence_id"] = event_payload.get("evidence_id") or event_id
            event_payload["evidence_status"] = "persisted"
            persist_alert = getattr(alert_manager, "persist_alert", None)
            if alert is not None and callable(persist_alert):
                alert_persisted = persist_alert(
                    alert,
                    event_id=event_id,
                    cooldown_key=confirmation_key,
                )
                event_payload["alert_persistence_status"] = "persisted" if alert_persisted else "failed"
            elif alert is not None:
                # Keep ingestion resilient when an embedding supplies only the
                # legacy in-memory alert interface. The production manager
                # always implements durable persistence.
                event_payload["alert_persistence_status"] = "unavailable"
        else:
            event_payload["evidence_id"] = None
            event_payload["incident_id"] = None
            event_payload["evidence_status"] = "failed"
            event_payload["alert_persistence_status"] = "unavailable"
        self._events.append(event_payload)
        get_state().add_event(event_payload)
        self._publish_confirmed_alert(event_payload)
        with self._lock:
            self._total_alerts += 1
            if risk_level in {"HIGH", "CRITICAL"}:
                self._high_risk_count += 1
        logger.info(
            "Generated alert camera_id=%s track_id=%s risk=%s score=%.3f frame=%s",
            camera_id,
            track_key,
            risk_level,
            risk_score,
            frame_number,
        )
        return event_payload

    @staticmethod
    def _publish_confirmed_alert(event: Dict[str, Any]) -> None:
        """Publish a finalized alert copy to the cross-process event stream.

        APIState remains the low-latency local UI source.  The Redis stream is
        a durable integration signal for other in-scope consumers and is
        intentionally published only after AlertManager approval and evidence
        persistence have completed.  A stream outage never blocks detection.
        """
        try:
            from aegis.core.events import get_event_bus

            # JSON round-tripping removes numpy/datetime values that msgpack
            # deployments cannot serialize, and prevents fallback streams from
            # mutating the APIState payload with their internal timestamp.
            stream_event = json.loads(json.dumps(dict(event), default=str))
            get_event_bus().publish("events", stream_event)
        except Exception as exc:
            logger.warning(
                "Confirmed alert event-stream publish failed event_id=%s: %s",
                event.get("event_id"),
                type(exc).__name__,
            )

    def _alert_confirmation_key(self, camera_id: str, track_payload: Dict[str, Any]) -> str:
        event_type = str(track_payload.get("threat_event_type") or "risk_alert")
        armed_track_id = str(
            track_payload.get("person_track_id")
            or track_payload.get("raw_track_id")
            or track_payload.get("track_id")
            or "untracked"
        )
        nearby_track_id = str(track_payload.get("nearby_person_track_id") or "none")
        if event_type == "possible_assault" and nearby_track_id != "none":
            armed_track_id, nearby_track_id = sorted((armed_track_id, nearby_track_id))
        # Weapon IDs are deliberately evidence, not cooldown identity. Small
        # objects are prone to tracker-ID churn and base/custom detectors may
        # observe the same object; the armed-person context must remain one
        # alert within the cooldown window.
        return ":".join((str(camera_id), event_type, armed_track_id, nearby_track_id))

    @staticmethod
    def _alert_title(track_payload: Dict[str, Any], risk_level: str) -> str:
        threat_event_type = str(track_payload.get("threat_event_type") or "")
        if threat_event_type == "possible_armed_threat":
            return "Possible armed threat"
        if threat_event_type == "possible_assault":
            return "Possible assault"
        return f"{risk_level} risk confirmed"

    def _save_event_snapshot(
        self,
        camera_id: str,
        event_id: str,
        timestamp: datetime,
        frame: np.ndarray,
    ) -> EventSnapshot:
        """Write exactly one compressed keyframe for an accepted alert.

        Frame capture happens only after the existing alert manager and its
        cooldown approve a HIGH/CRITICAL alert.  It is intentionally not part
        of normal per-frame detection persistence.
        """
        try:
            snapshot_dir = Path("data/output/snapshots")
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            safe_camera_id = re.sub(r"[^A-Za-z0-9_-]+", "-", str(camera_id)).strip("-_") or "camera"
            safe_event_id = re.sub(r"[^A-Za-z0-9_-]+", "-", str(event_id)).strip("-_") or "event"
            timestamp_token = timestamp.strftime("%Y%m%dT%H%M%S%fZ")
            filename = f"{safe_camera_id[:80]}_{safe_event_id[:128]}_{timestamp_token}.jpg"
            path = snapshot_dir / filename
            if cv2.imwrite(str(path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85]):
                return EventSnapshot(path=path.as_posix(), status="saved")
            logger.warning("Failed to encode event snapshot for event_id=%s", event_id)
        except Exception as exc:
            logger.warning("Failed to save event snapshot event_id=%s: %s", event_id, exc)
        return EventSnapshot(path=None, status="failed")

    def _persist_event(self, event: Dict[str, Any]) -> bool:
        try:
            from aegis.database.connection import get_db_session
            from aegis.database.persistence import get_persistence_status
            from aegis.database.repositories import (
                EventRepository,
                ObservationRepository,
                RiskAssessmentRepository,
            )

            raw_track_id = str(event.get("track_id", "")).split(":")[-1]
            track_id = int(raw_track_id) if raw_track_id.isdigit() else None
            with get_db_session() as session:
                persisted_event, created = EventRepository(session).create_or_get_evidence(
                    event_id=str(event["event_id"]),
                    event_type="risk_alert",
                    message=event["explanation"],
                    timestamp=datetime.fromisoformat(event["timestamp"]),
                    track_id=track_id,
                    track_key=event.get("track_id"),
                    alert_id=event.get("alert_id"),
                    camera_id=event.get("camera_id"),
                    camera_name=event.get("camera_name"),
                    object_class=event.get("object_class") or event.get("class_name"),
                    risk_level=event["risk_level"],
                    risk_score=event["risk_score"],
                    factors=event.get("factors", []),
                    zone=event.get("zone"),
                    zone_id=event.get("zone_id"),
                    zone_name=event.get("zone_name"),
                    bounding_box=event.get("bbox") or event.get("visual_evidence", {}).get("bbox"),
                    reason=event.get("reason") or event["explanation"],
                    snapshot_path=event.get("snapshot_path"),
                    snapshot_status=event.get("snapshot_status") or "unavailable",
                    clip_path=event.get("clip_path"),
                    metadata=event,
                )
                ObservationRepository(session).attach_to_event(
                    list(event.get("observation_ids") or []),
                    persisted_event.event_id,
                )
                # Correlation is a best-effort enrichment of already durable
                # evidence.  A failed incident write must never roll back the
                # alert evidence or interrupt the camera pipeline.
                try:
                    from aegis.intelligence.incident_correlation import IncidentCorrelationService

                    with session.begin_nested():
                        incident = IncidentCorrelationService(session).correlate_event(persisted_event)
                    if incident is not None:
                        event["incident_id"] = incident.incident_id
                        from aegis.intelligence.risk_assessment import persist_assessment

                        assessment, _ = persist_assessment(
                            RiskAssessmentRepository(session), incident, persisted_event
                        )
                        event["risk_assessment_id"] = assessment.assessment_id
                except Exception as correlation_error:
                    logger.warning(
                        "Incident correlation failed for event_id=%s: %s",
                        event["event_id"],
                        correlation_error,
                    )
                event["evidence_id"] = persisted_event.event_id
            get_persistence_status().record_success("camera_ingestion")
            if not created:
                logger.info("Skipped duplicate durable evidence event_id=%s", event["event_id"])
            return True
        except Exception as exc:
            # Camera ingestion remains non-blocking, but the operational view
            # must expose the failed durable write as degraded.
            try:
                from aegis.database.persistence import get_persistence_status

                get_persistence_status().record_failure("camera_ingestion", exc)
            except Exception:
                pass
            logger.warning("Event repository persistence failed: %s", exc)
            return False

    def _frame_explanation(self, tracks: List[Dict[str, Any]]) -> str:
        if not tracks:
            return "No tracked objects detected in this frame"
        top = max(tracks, key=lambda item: item.get("risk_score", 0.0))
        return top.get("risk_explanation") or "Tracked objects analyzed with no elevated risk signals"

    def _frame_verification_status(self, tracks: List[Dict[str, Any]]) -> str:
        if not tracks:
            return "confirmed"
        statuses = {str(item.get("verification_status", "needs_verification")) for item in tracks}
        if "confirmed" in statuses and len(statuses) == 1:
            return "confirmed"
        if "unsupported" in statuses:
            return "unsupported"
        if "candidate" in statuses:
            return "candidate"
        return "needs_verification"


class CameraHealthMonitor:
    def __init__(self, manager: "MultiCameraPipelineManager", interval_seconds: float = 2.0):
        self._manager = manager
        self._interval_seconds = interval_seconds
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="camera-health-monitor")
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _loop(self) -> None:
        while self._running:
            for source in self._manager.sources():
                source.check_health()
            time.sleep(self._interval_seconds)


class MultiCameraPipelineManager:
    def __init__(
        self,
        registry: Optional[CameraRegistry] = None,
        factory: Optional[CameraSourceFactory] = None,
        ingestion_service: Optional[FrameIngestionService] = None,
    ):
        self.registry = registry or CameraRegistry()
        self.factory = factory or CameraSourceFactory()
        self.ingestion = ingestion_service or FrameIngestionService()
        self._sources: Dict[str, BaseCameraSource] = {}
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._processing: Dict[str, bool] = {}
        self._last_submit: Dict[str, float] = {}
        self._events: Deque[Dict[str, Any]] = deque(maxlen=1000)
        self._lock = threading.RLock()
        self.health_monitor = CameraHealthMonitor(self)
        self.health_monitor.start()

        for config in self.registry.list():
            try:
                self._sources[config.camera_id] = self.factory.create(
                    config,
                    on_frame=self._handle_frame,
                    on_status_change=self._handle_status_change,
                )
            except Exception as exc:
                logger.error("Failed to restore camera %s: %s", config.camera_id, exc)

    def sources(self) -> Iterable[BaseCameraSource]:
        with self._lock:
            return list(self._sources.values())

    def list_cameras(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [self._camera_payload(source) for source in self._sources.values()]

    def create_camera(self, config: CameraConfig, auto_start: bool = False) -> Dict[str, Any]:
        config.camera_id = _safe_camera_id(config.camera_id)
        source = self.factory.create(
            config,
            on_frame=self._handle_frame,
            on_status_change=self._handle_status_change,
        )
        with self._lock:
            if config.camera_id in self._sources:
                raise ValueError(f"Camera {config.camera_id} already exists")
            self.registry.save(config)
            self._sources[config.camera_id] = source
        if auto_start and config.enabled:
            source.start()
        return self._camera_payload(source)

    def update_camera(self, camera_id: str, changes: Dict[str, Any]) -> Dict[str, Any]:
        existing = self.registry.get(camera_id)
        if existing is None:
            raise KeyError(camera_id)
        old_source = self.get_source(camera_id)
        was_running = old_source.is_running if old_source else False
        if old_source:
            old_source.stop()
        self._reset_ingestion_camera(camera_id)

        data = existing.to_private_dict()
        data.update({key: value for key, value in changes.items() if value is not None})
        data["camera_id"] = camera_id
        config = CameraConfig.from_dict(data)
        source = self.factory.create(
            config,
            on_frame=self._handle_frame,
            on_status_change=self._handle_status_change,
        )
        with self._lock:
            self.registry.save(config)
            self._sources[camera_id] = source
        if was_running:
            source.start()
        return self._camera_payload(source)

    def delete_camera(self, camera_id: str) -> bool:
        with self._lock:
            source = self._sources.pop(camera_id, None)
            deleted = self.registry.delete(camera_id)
        if source:
            source.stop()
        self._reset_ingestion_camera(camera_id)
        return deleted or source is not None

    def get_source(self, camera_id: str) -> Optional[BaseCameraSource]:
        with self._lock:
            return self._sources.get(camera_id)

    def get_camera(self, camera_id: str) -> Optional[Dict[str, Any]]:
        source = self.get_source(camera_id)
        return self._camera_payload(source) if source else None

    def start_camera(self, camera_id: str) -> Dict[str, Any]:
        source = self.get_source(camera_id)
        if source is None:
            raise KeyError(camera_id)
        source.start()
        return self._camera_payload(source)

    def stop_camera(self, camera_id: str) -> Dict[str, Any]:
        source = self.get_source(camera_id)
        if source is None:
            raise KeyError(camera_id)
        source.stop()
        self._reset_ingestion_camera(camera_id)
        return self._camera_payload(source)

    def _reset_ingestion_camera(self, camera_id: str) -> None:
        reset = getattr(self.ingestion, "reset_camera", None)
        if callable(reset):
            reset(camera_id)

    def get_status(self, camera_id: str) -> Dict[str, Any]:
        source = self.get_source(camera_id)
        if source is None:
            raise KeyError(camera_id)
        return source.get_status().to_dict()

    def get_snapshot(self, camera_id: str) -> Optional[bytes]:
        source = self.get_source(camera_id)
        if source is None:
            raise KeyError(camera_id)
        return source.get_snapshot_jpeg()

    def ingest_browser_frame(self, camera_id: str, base64_frame: str) -> Dict[str, Any]:
        source = self.get_source(camera_id)
        if source is None:
            raise KeyError(camera_id)
        if source.config.source_type != CameraSourceType.BROWSER_WEBCAM:
            raise ValueError("camera_id is not a BROWSER_WEBCAM source")
        frame = _decode_base64_frame(base64_frame)
        source.ingest_frame(frame, notify_pipeline=False)
        return self.ingestion.process_frame(camera_id, frame, source.config.metadata)

    def process_uploaded_video(self, video_id: str, upload_path: str, camera_id: Optional[str] = None) -> Dict[str, Any]:
        camera_id = _safe_camera_id(camera_id or f"video-{video_id}")
        config = CameraConfig(
            camera_id=camera_id,
            source_type=CameraSourceType.UPLOADED_VIDEO,
            name=f"Uploaded video {video_id}",
            upload_path=upload_path,
            video_id=video_id,
            enabled=True,
            max_retries=0,
        )
        if self.get_source(camera_id):
            self.delete_camera(camera_id)
        payload = self.create_camera(config, auto_start=True)
        return payload

    def get_camera_events(self, camera_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        risk_events = self.ingestion.get_camera_events(camera_id, limit=limit)
        return risk_events[-limit:]

    def get_camera_detections(self, camera_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return self.ingestion.get_camera_detections(camera_id, limit=limit)

    def get_object_registry(self, camera_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return get_state().get_object_registry(camera_id)

    def _handle_frame(self, camera_id: str, frame: np.ndarray) -> None:
        now = time.time()
        if self._processing.get(camera_id):
            return
        if now - self._last_submit.get(camera_id, 0.0) < 0.2:
            return
        self._last_submit[camera_id] = now
        self._processing[camera_id] = True

        def run() -> None:
            try:
                source = self.get_source(camera_id)
                metadata = source.config.metadata if source else None
                self.ingestion.process_frame(camera_id, frame, metadata)
            except Exception as exc:
                source = self.get_source(camera_id)
                if source:
                    source._set_status(CameraConnectionStatus.ERROR, f"Frame processing failed: {exc}")
                logger.exception("Frame processing failed for camera %s", camera_id)
            finally:
                self._processing[camera_id] = False

        self._executor.submit(run)

    def _handle_status_change(self, camera_id: str, status: CameraConnectionStatus, error: Optional[str]) -> None:
        self._events.append(
            {
                "camera_id": camera_id,
                "event_type": "status",
                "timestamp": datetime.utcnow().isoformat(),
                "status": status.value,
                "error_message": error,
            }
        )

    def _camera_payload(self, source: BaseCameraSource) -> Dict[str, Any]:
        return {
            **source.config.to_public_dict(),
            "runtime": source.get_status().to_dict(),
        }


def frame_to_data_url(jpeg_bytes: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode("ascii")
