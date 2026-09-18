"""
AegisAI - Camera Registry

Persistent storage for camera configurations using a JSON file.
Thread-safe for concurrent access from API and pipeline threads.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from aegis.camera.types import CameraConfig
from aegis.camera.utils import safe_camera_id

logger = logging.getLogger(__name__)


class CameraRegistry:
    """
    Persistent camera configuration registry.

    Stores camera configs in a JSON file so they survive restarts.
    Thread-safe for concurrent read/write access.
    """

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
            config.camera_id = safe_camera_id(config.camera_id)
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
        payload = {
            "cameras": [
                (
                    config.to_persisted_dict()
                    if hasattr(config, "to_persisted_dict")
                    else config.to_private_dict()
                )
                for config in self._configs.values()
            ]
        }
        temporary_path = self._storage_path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
        temporary_path.replace(self._storage_path)
        try:
            os.chmod(self._storage_path, 0o600)
        except OSError:
            pass
