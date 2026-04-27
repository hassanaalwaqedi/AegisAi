"""
AegisAI - Edge Pipeline Result Types

Data structures for the Phase 1 edge pipeline output.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from aegis.risk.proximity_risk import ProximityRiskAssessment


@dataclass
class PipelineResult:
    """
    Complete result from a single frame processed through the edge pipeline.

    Attributes:
        detections: Raw YOLO detections for this frame
        tracks: Tracked objects with stable IDs
        risk_assessment: Proximity-based risk assessment
        frame_id: Frame number
        camera_id: Source camera identifier
        processing_time_ms: Total pipeline processing time
    """
    detections: list = field(default_factory=list)
    tracks: list = field(default_factory=list)
    risk_assessment: Optional[ProximityRiskAssessment] = None
    frame_id: int = 0
    camera_id: str = "default"
    processing_time_ms: float = 0.0

    @property
    def detection_count(self) -> int:
        return len(self.detections)

    @property
    def track_count(self) -> int:
        return len(self.tracks)

    @property
    def risk_level(self) -> str:
        if self.risk_assessment:
            return self.risk_assessment.risk_level
        return "LOW"

    @property
    def risk_score(self) -> float:
        if self.risk_assessment:
            return self.risk_assessment.risk_score
        return 0.0

    def to_dict(self) -> dict:
        return {
            "frame_id": self.frame_id,
            "camera_id": self.camera_id,
            "detection_count": self.detection_count,
            "track_count": self.track_count,
            "risk_level": self.risk_level,
            "risk_score": round(self.risk_score, 3),
            "processing_time_ms": round(self.processing_time_ms, 1),
            "risk_assessment": self.risk_assessment.to_dict() if self.risk_assessment else None,
        }
