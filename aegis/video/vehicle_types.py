"""Typed, privacy-aware values used by optional vehicle enrichment.

The default public representation deliberately omits plate text, OCR candidates,
image hashes, and tracker scheduling details.  Those values are operationally
sensitive and must not leak through the normal tracks or detections APIs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class FrameQuality:
    accepted: bool
    sharpness: float = 0.0
    brightness: float = 0.0
    width: int = 0
    height: int = 0
    reason: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "sharpness": round(self.sharpness, 2),
            "brightness": round(self.brightness, 2),
            "width": self.width,
            "height": self.height,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class OCRCandidate:
    text: str
    confidence: Optional[float] = None


@dataclass(frozen=True)
class PlateValidation:
    valid: bool
    normalized: Optional[str] = None
    reason: Optional[str] = None


@dataclass(frozen=True)
class PlateRecognitionResult:
    available: bool
    valid: bool = False
    plate_text: Optional[str] = None  # Restricted backend-only data.
    confidence: Optional[float] = None
    reason: Optional[str] = None


@dataclass(frozen=True)
class ColorEstimate:
    label: str = "unknown"
    confidence: Optional[float] = None
    reason: Optional[str] = None


@dataclass(frozen=True)
class MakeModelEstimate:
    available: bool = False
    make: Optional[str] = None
    model: Optional[str] = None
    confidence: Optional[float] = None
    reason: Optional[str] = "model_not_configured"


@dataclass(frozen=True)
class DeduplicationDecision:
    skip: bool
    reason: Optional[str] = None


@dataclass
class VehicleEnrichmentResult:
    """Internal result.  Use :meth:`to_public_dict` outside privileged code."""

    status: str
    quality: FrameQuality
    reason: Optional[str] = None
    color: ColorEstimate = field(default_factory=ColorEstimate)
    plate: PlateRecognitionResult = field(
        default_factory=lambda: PlateRecognitionResult(available=False, reason="disabled")
    )
    make_model: MakeModelEstimate = field(default_factory=MakeModelEstimate)
    deduplication: Optional[DeduplicationDecision] = None
    evidence_saved: bool = False

    def to_public_dict(self) -> dict[str, Any]:
        """Return only non-sensitive enrichment state for operator APIs."""
        result: dict[str, Any] = {
            "status": self.status,
            "reason": self.reason,
            "evidence_quality": self.quality.to_dict(),
            "color": {
                "label": self.color.label,
                "confidence": self.color.confidence,
                "reason": self.color.reason,
            },
            "plate": {
                "available": self.plate.available,
                "validation_status": "valid" if self.plate.valid else "not_available",
                "reason": self.plate.reason,
            },
            "make_model": {
                "available": self.make_model.available,
                "reason": self.make_model.reason,
            },
            "evidence_saved": self.evidence_saved,
        }
        if self.deduplication:
            result["deduplication"] = {
                "skipped": self.deduplication.skip,
                "reason": self.deduplication.reason,
            }
        return result
