"""
AegisAI - Cloud Communication Types

Data structures for cloud API communication.
Defines the contract between edge and cloud layers.

Phase 6: Edge/Cloud Hybrid Intelligence
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple


@dataclass
class CloudVerdict:
    """
    Enhanced risk assessment returned by the cloud layer.
    
    The cloud runs heavy models (CLIP, SAM, MiDaS, SlowFast) 
    and returns a refined threat assessment.
    
    Attributes:
        event_id: Matching event ID from the edge request
        enhanced_risk_score: Cloud-refined risk score (0.0 - 1.0)
        risk_level: Risk level string (LOW/MEDIUM/HIGH/CRITICAL)
        threat_type: Classified threat type
        weapon_type: Specific weapon identified
        holding_confidence: Confidence that person is holding weapon
        action_detected: Detected action (walk/run/aim/attack)
        context_description: CLIP-generated scene description
        depth_distances: Object distance measurements in meters
        explanation: Human-readable explanation of verdict
        models_used: Which cloud models contributed
        processing_time_ms: Cloud processing latency
    """
    event_id: str = ""
    enhanced_risk_score: float = 0.0
    risk_level: str = "LOW"
    threat_type: Optional[str] = None
    weapon_type: Optional[str] = None
    holding_confidence: float = 0.0
    action_detected: Optional[str] = None
    context_description: str = ""
    depth_distances: Dict[str, float] = field(default_factory=dict)
    explanation: str = ""
    models_used: List[str] = field(default_factory=list)
    processing_time_ms: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "enhanced_risk_score": round(self.enhanced_risk_score, 3),
            "risk_level": self.risk_level,
            "threat_type": self.threat_type,
            "weapon_type": self.weapon_type,
            "holding_confidence": round(self.holding_confidence, 3),
            "action_detected": self.action_detected,
            "context_description": self.context_description,
            "depth_distances": {k: round(v, 2) for k, v in self.depth_distances.items()},
            "explanation": self.explanation,
            "models_used": self.models_used,
            "processing_time_ms": round(self.processing_time_ms, 1),
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'CloudVerdict':
        """Deserialize from API response."""
        return cls(
            event_id=data.get("event_id", ""),
            enhanced_risk_score=data.get("enhanced_risk_score", 0.0),
            risk_level=data.get("risk_level", "LOW"),
            threat_type=data.get("threat_type"),
            weapon_type=data.get("weapon_type"),
            holding_confidence=data.get("holding_confidence", 0.0),
            action_detected=data.get("action_detected"),
            context_description=data.get("context_description", ""),
            depth_distances=data.get("depth_distances", {}),
            explanation=data.get("explanation", ""),
            models_used=data.get("models_used", []),
            processing_time_ms=data.get("processing_time_ms", 0.0),
        )
    
    @property
    def is_threat(self) -> bool:
        """Check if this verdict indicates a real threat."""
        return self.risk_level in ("HIGH", "CRITICAL")
