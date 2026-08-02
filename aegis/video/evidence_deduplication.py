"""Near-duplicate candidate suppression for the same camera and track."""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Optional

import numpy as np

from aegis.video.vehicle_types import DeduplicationDecision


class EvidenceDeduplicator:
    def __init__(self, *, enabled: bool = True, max_distance: int = 8, retention_seconds: float = 180.0, cache_limit: int = 500) -> None:
        self.enabled = enabled
        self.max_distance = max_distance
        self.retention_seconds = retention_seconds
        self.cache_limit = cache_limit
        self._recent: OrderedDict[tuple[str, str], tuple[float, object]] = OrderedDict()

    def should_store(self, camera_id: str, track_id: str, frame: np.ndarray, *, manual: bool = False, high_priority: bool = False, now: Optional[float] = None) -> DeduplicationDecision:
        if manual:
            return DeduplicationDecision(False, "manual_evidence")
        if high_priority:
            return DeduplicationDecision(False, "high_priority_evidence")
        if not self.enabled:
            return DeduplicationDecision(False, "disabled")
        try:
            from PIL import Image
            import imagehash
            fingerprint = imagehash.phash(Image.fromarray(frame[:, :, ::-1] if frame.ndim == 3 else frame))
        except ImportError:
            return DeduplicationDecision(False, "imagehash_unavailable")
        current = time.monotonic() if now is None else now
        self._prune(current)
        key = (camera_id, track_id)
        prior = self._recent.get(key)
        if prior and abs(prior[1] - fingerprint) <= self.max_distance:
            return DeduplicationDecision(True, "near_duplicate")
        self._recent[key] = (current, fingerprint)
        self._recent.move_to_end(key)
        while len(self._recent) > self.cache_limit:
            self._recent.popitem(last=False)
        return DeduplicationDecision(False, "new_evidence")

    def _prune(self, current: float) -> None:
        expired = [key for key, (saved, _) in self._recent.items() if current - saved > self.retention_seconds]
        for key in expired:
            self._recent.pop(key, None)
