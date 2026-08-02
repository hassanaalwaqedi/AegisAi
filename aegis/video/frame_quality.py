"""Objective crop-quality checks used before costly vehicle enrichment."""

from __future__ import annotations

import cv2
import numpy as np

from aegis.video.vehicle_types import FrameQuality


class FrameQualityGate:
    def __init__(
        self,
        *,
        min_width: int = 160,
        min_height: int = 80,
        min_sharpness: float = 80.0,
        min_brightness: float = 35.0,
    ) -> None:
        self.min_width = min_width
        self.min_height = min_height
        self.min_sharpness = min_sharpness
        self.min_brightness = min_brightness

    def evaluate(self, crop: np.ndarray | None) -> FrameQuality:
        if crop is None or not isinstance(crop, np.ndarray) or crop.ndim not in (2, 3) or crop.size == 0:
            return FrameQuality(accepted=False, reason="invalid_crop")
        height, width = crop.shape[:2]
        if width < self.min_width or height < self.min_height:
            return FrameQuality(accepted=False, width=width, height=height, reason="too_small")
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
        brightness = float(np.mean(gray))
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        if brightness < self.min_brightness:
            return FrameQuality(False, sharpness, brightness, width, height, "low_light")
        if sharpness < self.min_sharpness:
            return FrameQuality(False, sharpness, brightness, width, height, "too_blurry")
        return FrameQuality(True, sharpness, brightness, width, height)
