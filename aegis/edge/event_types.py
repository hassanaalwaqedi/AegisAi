"""
AegisAI - Edge Event Types

Data structures for edge risk assessment and cloud escalation events.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple


@dataclass
class TrackSummary:
    """
    Lightweight summary of a tracked object for cloud transmission.
    
    Attributes:
        track_id: Unique tracker-assigned ID
        class_name: Detected class name
        class_id: COCO class identifier
        confidence: Detection confidence
        bbox: Bounding box (x1, y1, x2, y2)
        object_category: person/weapon/vehicle/animal/generic
        is_weapon: Whether this is a weapon detection
        is_person: Whether this is a person detection
        is_animal: Whether this is an animal detection
    """
    track_id: Optional[int]
    class_name: str
    class_id: int
    confidence: float
    bbox: Tuple[int, int, int, int]
    object_category: str = "generic"
    is_weapon: bool = False
    is_person: bool = False
    is_animal: bool = False
    
    def to_dict(self) -> dict:
        return {
            "track_id": self.track_id,
            "class_name": self.class_name,
            "class_id": self.class_id,
            "confidence": round(self.confidence, 3),
            "bbox": list(self.bbox),
            "object_category": self.object_category,
            "is_weapon": self.is_weapon,
            "is_person": self.is_person,
            "is_animal": self.is_animal,
        }


@dataclass
class EdgeAssessment:
    """
    Result of edge-level risk assessment for a single frame.
    
    Attributes:
        risk_score: Combined risk score (0.0 - 1.0)
        triggers: List of triggered risk rules
        should_escalate: Whether to send this to cloud
        track_summaries: Lightweight track data
        frame_id: Frame number
        timestamp: Assessment time
    """
    risk_score: float
    triggers: List[str] = field(default_factory=list)
    should_escalate: bool = False
    track_summaries: List[TrackSummary] = field(default_factory=list)
    frame_id: int = 0
    timestamp: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            "risk_score": round(self.risk_score, 3),
            "triggers": self.triggers,
            "should_escalate": self.should_escalate,
            "tracks": [t.to_dict() for t in self.track_summaries],
            "frame_id": self.frame_id,
            "timestamp": self.timestamp,
        }


@dataclass
class SuspiciousEvent:
    """
    A suspicious event to be sent to the cloud for deep analysis.
    
    Contains a compressed frame and metadata about detected threats.
    
    Attributes:
        event_id: Unique event identifier
        camera_id: Source camera
        timestamp: Event time
        frame_jpeg: JPEG-compressed frame bytes
        tracks: Lightweight track summaries
        edge_risk_score: Risk score from edge filter
        triggers: What triggered escalation
        frame_id: Source frame number
        frame_width: Original frame width
        frame_height: Original frame height
    """
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    camera_id: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    frame_jpeg: bytes = b""
    tracks: List[TrackSummary] = field(default_factory=list)
    edge_risk_score: float = 0.0
    triggers: List[str] = field(default_factory=list)
    frame_id: int = 0
    frame_width: int = 0
    frame_height: int = 0
    
    def to_dict(self) -> dict:
        """Serialize for API transmission (without frame bytes)."""
        return {
            "event_id": self.event_id,
            "camera_id": self.camera_id,
            "timestamp": self.timestamp.isoformat(),
            "tracks": [t.to_dict() for t in self.tracks],
            "edge_risk_score": round(self.edge_risk_score, 3),
            "triggers": self.triggers,
            "frame_id": self.frame_id,
            "frame_width": self.frame_width,
            "frame_height": self.frame_height,
        }
