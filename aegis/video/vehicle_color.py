"""Conservative HSV vehicle-color estimator, designed to prefer unknown."""

from __future__ import annotations

import cv2
import numpy as np

from aegis.video.vehicle_types import ColorEstimate, FrameQuality


class VehicleColorService:
    def __init__(self, enabled: bool = False, min_saturation: int = 35) -> None:
        self.enabled = enabled
        self.min_saturation = min_saturation

    def estimate(self, crop: np.ndarray, quality: FrameQuality) -> ColorEstimate:
        if not self.enabled:
            return ColorEstimate(reason="disabled")
        if not quality.accepted:
            return ColorEstimate(reason=quality.reason)
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        hue, saturation, value = (float(np.median(hsv[:, :, index])) for index in range(3))
        if value < 50 or saturation < self.min_saturation:
            if value < 50:
                return ColorEstimate("unknown", reason="low_light")
            if value > 185:
                return ColorEstimate("white", 0.6)
            return ColorEstimate("gray", 0.55)
        palettes = (("red", ((hue <= 10) or (hue >= 170))), ("orange", 10 < hue <= 25), ("yellow", 25 < hue <= 35), ("green", 35 < hue <= 85), ("blue", 85 < hue <= 135), ("purple", 135 < hue < 170))
        for label, matches in palettes:
            if matches:
                confidence = min(0.85, 0.45 + saturation / 510.0)
                return ColorEstimate(label, round(confidence, 2))
        return ColorEstimate("unknown", reason="ambiguous_color")
