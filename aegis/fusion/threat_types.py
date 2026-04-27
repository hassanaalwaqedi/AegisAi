"""
AegisAI - Threat Assessment Types

Data structures for multi-model threat fusion output.
Used by the cloud-side Risk Fusion Engine.

Phase 6: Edge/Cloud Hybrid Intelligence
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class ThreatAssessment:
    """
    Unified threat assessment produced by multi-model fusion.
    
    Combines signals from all cloud models into a single
    coherent threat description.
    
    Attributes:
        track_id: Tracked object ID
        person_class: Person sub-class if applicable
        weapon_type: Detected weapon type (gun, knife, None)
        weapon_distance_m: Distance between weapon and person in meters
        holding_confidence: Fused confidence person is holding weapon (0-1)
        action: Recognized action (walking, running, aiming, attacking)
        behavior: High-level behavior (approaching, stationary, fleeing)
        risk_level: Final risk level
        risk_score: Final risk score (0-1)
        explanation: Human-readable explanation
        position_3d: Estimated 3D position (X, Y, Z) if depth available
        contributing_models: Which models contributed to this assessment
        model_scores: Per-model confidence scores
    """
    track_id: Optional[int] = None
    person_class: str = "person"
    weapon_type: Optional[str] = None
    weapon_distance_m: Optional[float] = None
    holding_confidence: float = 0.0
    action: Optional[str] = None
    behavior: str = "unknown"
    risk_level: str = "LOW"
    risk_score: float = 0.0
    explanation: str = ""
    position_3d: Optional[Tuple[float, float, float]] = None
    contributing_models: List[str] = field(default_factory=list)
    model_scores: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "track_id": self.track_id,
            "person_class": self.person_class,
            "weapon_type": self.weapon_type,
            "weapon_distance_m": round(self.weapon_distance_m, 2) if self.weapon_distance_m else None,
            "holding_confidence": round(self.holding_confidence, 3),
            "action": self.action,
            "behavior": self.behavior,
            "risk_level": self.risk_level,
            "risk_score": round(self.risk_score, 3),
            "explanation": self.explanation,
            "position_3d": list(self.position_3d) if self.position_3d else None,
            "contributing_models": self.contributing_models,
            "model_scores": {k: round(v, 3) for k, v in self.model_scores.items()},
        }
