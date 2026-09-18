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
            # Keep the same local, deterministic behaviour when the optional
            # imagehash package is absent.  This is a compact average-hash,
            # not an AI inference or fabricated evidence decision.
            grayscale = frame.mean(axis=2) if frame.ndim == 3 else frame
            height, width = grayscale.shape[:2]
            if height == 0 or width == 0:
                return DeduplicationDecision(False, "invalid_frame")
            y_indices = np.linspace(0, height - 1, num=8, dtype=int)
            x_indices = np.linspace(0, width - 1, num=8, dtype=int)
            thumbnail = grayscale[np.ix_(y_indices, x_indices)]
            fingerprint = int("".join("1" if value >= thumbnail.mean() else "0" for value in thumbnail.ravel()), 2)
        current = time.monotonic() if now is None else now
        self._prune(current)
        key = (camera_id, track_id)
        prior = self._recent.get(key)
        if prior and self._distance(prior[1], fingerprint) <= self.max_distance:
            return DeduplicationDecision(True, "near_duplicate")
        self._recent[key] = (current, fingerprint)
        self._recent.move_to_end(key)
        while len(self._recent) > self.cache_limit:
            self._recent.popitem(last=False)
        return DeduplicationDecision(False, "new_evidence")

    @staticmethod
    def _distance(first: object, second: object) -> int:
        """Return a Hamming-style distance for imagehash and local hashes."""
        if isinstance(first, int) and isinstance(second, int):
            return (first ^ second).bit_count()
        return int(abs(first - second))

    def _prune(self, current: float) -> None:
        expired = [key for key, (saved, _) in self._recent.items() if current - saved > self.retention_seconds]
        for key in expired:
            self._recent.pop(key, None)
