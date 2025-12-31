"""
AegisAI - Smart City Risk Intelligence System
Risk Module - Shared Types

This module defines all shared data structures for the Risk Intelligence Layer.
Provides standardized containers for risk scores, levels, and explanations.

Phase 3: Risk Intelligence Layer
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from enum import Enum, auto


class RiskLevel(Enum):
    """
    Risk severity levels for decision-making.
    
    Attributes:
        LOW: Normal activity, monitoring only
        MEDIUM: Suspicious activity, flagged for review
        HIGH: Concerning activity, alert recommended
        CRITICAL: Immediate attention required
    """
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    
    @classmethod
    def from_score(cls, score: float, thresholds: 'RiskThresholds') -> 'RiskLevel':
        """
        Map a risk score to a risk level.
        
        Args:
            score: Risk score between 0.0 and 1.0
            thresholds: Threshold configuration
            
        Returns:
            Corresponding RiskLevel
        """
        if score >= thresholds.critical:
            return cls.CRITICAL
        elif score >= thresholds.high:
            return cls.HIGH
        elif score >= thresholds.medium:
            return cls.MEDIUM
        return cls.LOW
    
    @property
    def color_bgr(self) -> Tuple[int, int, int]:
        """Get BGR color for visualization."""
        colors = {
            RiskLevel.LOW: (0, 180, 0),       # Green
            RiskLevel.MEDIUM: (0, 180, 255),  # Orange
            RiskLevel.HIGH: (0, 0, 255),      # Red
            RiskLevel.CRITICAL: (128, 0, 255) # Purple/Magenta
        }
        return colors.get(self, (128, 128, 128))


@dataclass(frozen=True)
class RiskThresholds:
    """
    Configurable thresholds for risk level mapping.
    
    Attributes:
        medium: Score threshold for MEDIUM level
        high: Score threshold for HIGH level
        critical: Score threshold for CRITICAL level
    """
    medium: float = 0.25
    high: float = 0.50
    critical: float = 0.75


@dataclass
class RiskFactor:
    """
    A single contributing factor to the risk score.
    
    Attributes:
        name: Factor identifier (e.g., "loitering", "speed_anomaly")
        display_name: Human-readable name
        weight: Configured weight for this factor
        raw_value: Raw signal value before weighting
        weighted_value: Value after applying weight
        description: Optional explanation of this factor
    """
    name: str
    display_name: str
    weight: float
    raw_value: float
    weighted_value: float
    description: str = ""
    
    @property
    def contribution_percent(self) -> float:
        """Get contribution as percentage of total possible."""
        return self.weighted_value * 100


@dataclass
class RiskExplanation:
    """
    Human-readable explanation of a risk score.
    
    Attributes:
        summary: One-line summary of the risk
        factors: List of contributing factors
        recommendations: Suggested actions
    """
    summary: str
    factors: List[RiskFactor] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    
    @property
    def primary_factors(self) -> List[str]:
        """Get names of top contributing factors."""
        sorted_factors = sorted(
            self.factors, 
            key=lambda f: f.weighted_value, 
            reverse=True
        )
        return [f.display_name for f in sorted_factors[:3] if f.weighted_value > 0]
    
    def to_string(self) -> str:
        """Generate full explanation string."""
        parts = [self.summary]
        
        if self.factors:
            factor_strs = [f.display_name for f in self.factors if f.weighted_value > 0.01]
            if factor_strs:
                parts.append(f"Factors: {', '.join(factor_strs)}")
        
        return " | ".join(parts)


@dataclass
class RiskScore:
    """
    Complete risk assessment for a single track.
    
    Attributes:
        track_id: Unique identifier for the track
        score: Numerical risk score (0.0 to 1.0)
        level: Categorical risk level
        explanation: Human-readable explanation
        zone_multiplier: Applied zone-based multiplier
        temporal_adjustment: Applied temporal adjustment
        base_score: Score before adjustments
        timestamp: When this score was computed
    """
    track_id: int
    score: float
    level: RiskLevel
    explanation: RiskExplanation
    zone_multiplier: float = 1.0
    temporal_adjustment: float = 0.0
    base_score: float = 0.0
    timestamp: float = 0.0
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "track_id": self.track_id,
            "risk_score": round(self.score, 3),
            "risk_level": self.level.value,
            "factors": [f.display_name for f in self.explanation.factors 
                       if f.weighted_value > 0.01],
            "explanation": self.explanation.summary
        }
    
    @property
    def is_concerning(self) -> bool:
        """Check if risk level warrants attention."""
        return self.level in (RiskLevel.HIGH, RiskLevel.CRITICAL)


@dataclass
class FrameRiskSummary:
    """
    Aggregated risk summary for an entire frame.
    
    Attributes:
        frame_id: Frame number
        timestamp: Frame timestamp
        track_risks: List of RiskScore for all tracks
        max_risk_score: Highest risk score in frame
        max_risk_level: Highest risk level in frame
        concerning_tracks: Number of HIGH/CRITICAL tracks
        total_tracks: Total assessed tracks
    """
    frame_id: int
    timestamp: float
    track_risks: List[RiskScore] = field(default_factory=list)
    max_risk_score: float = 0.0
    max_risk_level: RiskLevel = RiskLevel.LOW
    concerning_tracks: int = 0
    total_tracks: int = 0
    
    def get_risk(self, track_id: int) -> Optional[RiskScore]:
        """Get risk score for a specific track."""
        for risk in self.track_risks:
            if risk.track_id == track_id:
                return risk
        return None
    
    @property
    def has_concerns(self) -> bool:
        """Check if any tracks have concerning risk levels."""
        return self.concerning_tracks > 0
