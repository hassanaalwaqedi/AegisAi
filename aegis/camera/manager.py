"""
AegisAI - Multi-Camera Pipeline Manager

Orchestrates multiple camera sources with centralized health monitoring,
frame processing delegation, and lifecycle management.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Deque, Dict, Iterable, List, Optional

import numpy as np

from aegis.api.state import get_state
from aegis.camera.base import BaseCameraSource
from aegis.camera.factory import CameraSourceFactory
from aegis.camera.registry import CameraRegistry
from aegis.camera.types import (
    CameraConfig,
    CameraConnectionStatus,
    CameraSourceType,
)
from aegis.camera.utils import decode_base64_frame, safe_camera_id

logger = logging.getLogger(__name__)


def configured_inference_workers() -> int:
    """Return a bounded worker count for CPU-intensive camera inference.

    Per-camera submissions are already coalesced while processing is active,
    so one worker keeps an overloaded local machine responsive without an
    unbounded backlog. A dedicated host can opt into up to four workers.
    """
    raw_value = os.getenv("AEGIS_CAMERA_INFERENCE_WORKERS", "1")
    try:
        requested = int(raw_value)
    except (TypeError, ValueError):
        requested = 1
    return max(1, min(requested, 4))


class CameraHealthMonitor:
    """Periodically checks camera sources for stale frames."""

    def __init__(
        self, manager: "MultiCameraPipelineManager", interval_seconds: float = 2.0
    ):
        self._manager = manager
        self._interval_seconds = interval_seconds
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="camera-health-monitor"
        )
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
    """
    Manages multiple camera sources with lifecycle control.

    Provides CRUD operations for cameras, delegates frame processing
    to FrameIngestionService, and monitors camera health.
    """

    def __init__(
        self,
        registry: Optional[CameraRegistry] = None,
        factory: Optional[CameraSourceFactory] = None,
        ingestion_service: Optional[Any] = None,
    ):
        self.registry = registry or CameraRegistry()
        self.factory = factory or CameraSourceFactory()

        # Lazy import to avoid circular dependency
        if ingestion_service is not None:
            self.ingestion = ingestion_service
        else:
            from aegis.video.camera_sources import FrameIngestionService
            self.ingestion = FrameIngestionService()

        self._sources: Dict[str, BaseCameraSource] = {}
        self._executor = ThreadPoolExecutor(max_workers=configured_inference_workers())
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

    def create_camera(
        self, config: CameraConfig, auto_start: bool = False
    ) -> Dict[str, Any]:
        config.camera_id = safe_camera_id(config.camera_id)
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

    def update_camera(
        self, camera_id: str, changes: Dict[str, Any]
    ) -> Dict[str, Any]:
        existing = self.registry.get(camera_id)
        if existing is None:
            raise KeyError(camera_id)
        old_source = self.get_source(camera_id)
        was_running = old_source.is_running if old_source else False
        if old_source:
            old_source.stop()

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
        return self._camera_payload(source)

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

    def ingest_browser_frame(
        self, camera_id: str, base64_frame: str
    ) -> Dict[str, Any]:
        source = self.get_source(camera_id)
        if source is None:
            raise KeyError(camera_id)
        if source.config.source_type != CameraSourceType.BROWSER_WEBCAM:
            raise ValueError("camera_id is not a BROWSER_WEBCAM source")
        frame = decode_base64_frame(base64_frame)
        source.ingest_frame(frame, notify_pipeline=False)
        return self.ingestion.process_frame(camera_id, frame, source.config.metadata)

    def process_uploaded_video(
        self,
        video_id: str,
        upload_path: str,
        camera_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        camera_id = safe_camera_id(camera_id or f"video-{video_id}")
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

    def get_camera_events(
        self, camera_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        risk_events = self.ingestion.get_camera_events(camera_id, limit=limit)
        return risk_events[-limit:]

    def get_camera_detections(
        self, camera_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        return self.ingestion.get_camera_detections(camera_id, limit=limit)

    def get_object_registry(
        self, camera_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
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
                    source._set_status(
                        CameraConnectionStatus.ERROR,
                        f"Frame processing failed: {exc}",
                    )
                logger.exception(
                    "Frame processing failed for camera %s", camera_id
                )
            finally:
                self._processing[camera_id] = False

        self._executor.submit(run)

    def _handle_status_change(
        self,
        camera_id: str,
        status: CameraConnectionStatus,
        error: Optional[str],
    ) -> None:
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
