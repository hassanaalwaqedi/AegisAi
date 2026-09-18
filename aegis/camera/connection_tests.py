"""Structured, short-lived camera connection test results."""

from __future__ import annotations

import base64
import hashlib
import socket
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Dict, Optional
from urllib.parse import urlparse

import cv2
import numpy as np

from aegis.camera.types import CameraConfig
from aegis.camera.utils import mask_url


@dataclass
class CameraConnectionTestResult:
    ok: bool
    status: str
    error_category: Optional[str] = None
    error_message: Optional[str] = None
    dns_resolved: Optional[bool] = None
    host_reachable: Optional[bool] = None
    time_to_first_frame_ms: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    masked_url: Optional[str] = None
    snapshot_data_url: Optional[str] = None

    def to_public_dict(self) -> Dict[str, object]:
        return {
            "ok": self.ok,
            "status": self.status,
            "error_category": self.error_category,
            "error_message": self.error_message,
            "dns_resolved": self.dns_resolved,
            "host_reachable": self.host_reachable,
            "time_to_first_frame_ms": self.time_to_first_frame_ms,
            "width": self.width,
            "height": self.height,
            "masked_url": self.masked_url,
            "snapshot_data_url": self.snapshot_data_url,
        }

    def to_persisted_summary(self) -> Dict[str, object]:
        data = self.to_public_dict()
        data.pop("snapshot_data_url", None)
        return data


def endpoint_probe(raw_url: Optional[str], timeout_seconds: float) -> Dict[str, object]:
    """Best-effort DNS/TCP diagnostics; unavailable means not detectable."""
    if not raw_url:
        return {"dns_resolved": None, "host_reachable": None}
    parsed = urlparse(raw_url)
    host = parsed.hostname
    if not host:
        return {"dns_resolved": False, "host_reachable": False, "category": "invalid_url"}
    try:
        port = parsed.port or (554 if parsed.scheme.lower() in {"rtsp", "rtsps"} else 443)
    except ValueError:
        return {
            "dns_resolved": False,
            "host_reachable": False,
            "category": "invalid_url",
            "message": "Camera URL contains an invalid port.",
        }
    try:
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return {
            "dns_resolved": False,
            "host_reachable": False,
            "category": "dns_failed",
            "message": "Camera host could not be resolved.",
        }
    except OSError:
        return {"dns_resolved": None, "host_reachable": None}

    try:
        address = addresses[0][4]
        with socket.create_connection(address, timeout=max(0.25, min(timeout_seconds, 5.0))):
            return {"dns_resolved": True, "host_reachable": True}
    except socket.timeout:
        return {
            "dns_resolved": True,
            "host_reachable": False,
            "category": "timeout",
            "message": "Timed out reaching the camera RTSP port.",
        }
    except OSError:
        return {
            "dns_resolved": True,
            "host_reachable": False,
            "category": "host_unreachable",
            "message": "Camera host or RTSP port is unreachable.",
        }


def frame_snapshot_data_url(frame: np.ndarray) -> Optional[str]:
    """Return a bounded JPEG preview for a successful, transient test result."""
    try:
        height, width = frame.shape[:2]
        if width > 640:
            scaled_height = max(1, round(height * (640 / width)))
            frame = cv2.resize(frame, (640, scaled_height))
        ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if not ok:
            return None
        return "data:image/jpeg;base64," + base64.b64encode(encoded.tobytes()).decode("ascii")
    except Exception:
        return None


def result_for_invalid_url(raw_url: Optional[str], message: str) -> CameraConnectionTestResult:
    return CameraConnectionTestResult(
        ok=False,
        status="failed",
        error_category="invalid_url",
        error_message=message,
        masked_url=mask_url(raw_url),
    )


class CameraConnectionTestStore:
    """Short-lived proof that a specific source configuration passed a test."""

    def __init__(self, ttl_seconds: float = 300.0):
        self._ttl_seconds = ttl_seconds
        self._entries: Dict[str, tuple[float, str, CameraConnectionTestResult]] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _fingerprint(config: CameraConfig) -> str:
        raw = "|".join(
            [
                config.source_type.value,
                config.camera_id.strip(),
                config.url or "",
                str(config.device_index if config.device_index is not None else ""),
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def record(self, config: CameraConfig, result: CameraConnectionTestResult) -> str:
        token = uuid.uuid4().hex
        with self._lock:
            self._prune(time.monotonic())
            self._entries[token] = (time.monotonic(), self._fingerprint(config), result)
        return token

    def verified_result(
        self, token: Optional[str], config: CameraConfig
    ) -> Optional[CameraConnectionTestResult]:
        if not token:
            return None
        with self._lock:
            self._prune(time.monotonic())
            entry = self._entries.get(token)
            if not entry:
                return None
            _, fingerprint, result = entry
            if fingerprint != self._fingerprint(config) or not result.ok:
                return None
            return result

    def _prune(self, now: float) -> None:
        self._entries = {
            key: value
            for key, value in self._entries.items()
            if now - value[0] <= self._ttl_seconds
        }


_test_store: Optional[CameraConnectionTestStore] = None


def get_connection_test_store() -> CameraConnectionTestStore:
    global _test_store
    if _test_store is None:
        _test_store = CameraConnectionTestStore()
    return _test_store
