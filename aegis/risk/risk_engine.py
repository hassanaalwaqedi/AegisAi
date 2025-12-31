"""
AegisAI - Smart City Risk Intelligence System
Risk Engine Module

This module provides the core risk scoring logic.
Combines multiple signals into context-aware, explainable risk scores.

Features:
- Multi-signal risk computation
- Zone-based context weighting
- Temporal risk adjustment
- Mandatory explainability
- Deterministic scoring

Phase 3: Risk Intelligence Layer
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from aegis.risk.risk_types import (
    RiskLevel,
    RiskThresholds,
    RiskFactor,
    RiskExplanation,
    RiskScore,
    FrameRiskSummary
)
from aegis.risk.zone_context import ZoneManager, ZoneContext, ZoneType
from aegis.risk.temporal_model import TemporalRiskModel, TemporalConfig
from aegis.analysis.analysis_types import TrackAnalysis, CrowdMetrics, BehaviorFlags

# Configure module logger
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RiskWeights:
    """
    Signal weights for risk score computation.
    
    All weights should sum to approximately 1.0 for proper scoring.
    
    Attributes:
        loitering: Weight for loitering behavior
        speed_anomaly: Weight for sudden speed changes
        direction_change: Weight for direction reversals
        crowd_density: Weight for high crowd density
        zone_context: Weight for zone-based risk
        erratic_motion: Weight for erratic movement
        running: Weight for running (persons)
    """
    loitering: float = 0.25
    speed_anomaly: float = 0.18
    direction_change: float = 0.15
    crowd_density: float = 0.12
    zone_context: float = 0.15
    erratic_motion: float = 0.10
    running: float = 0.05
    
    @property
    def total(self) -> float:
        """Get sum of all weights."""
        return (
            self.loitering + self.speed_anomaly + self.direction_change +
            self.crowd_density + self.zone_context + self.erratic_motion +
            self.running
        )


@dataclass
class RiskEngineConfig:
    """
    Configuration for the risk engine.
    
    Attributes:
        weights: Signal weights
        thresholds: Risk level thresholds
        temporal: Temporal model configuration
        use_zones: Whether to apply zone-based weighting
        use_temporal: Whether to apply temporal adjustment
        normalize_crowd_at: Crowd density value for full contribution
    """
    weights: RiskWeights = field(default_factory=RiskWeights)
    thresholds: RiskThresholds = field(default_factory=RiskThresholds)
    temporal: TemporalConfig = field(default_factory=TemporalConfig)
    use_zones: bool = True
    use_temporal: bool = True
    normalize_crowd_at: int = 10


class RiskEngine:
    """
    Core risk scoring engine.
    
    Computes context-aware, explainable risk scores from behavioral analysis.
    
    Attributes:
        config: Engine configuration
        zone_manager: Zone context manager
        temporal_model: Temporal risk model
        
    Example:
        >>> engine = RiskEngine()
        >>> risk = engine.compute_risk(track_analysis, crowd_metrics, frame_id, timestamp)
        >>> print(f"Risk: {risk.score:.2f} ({risk.level.value})")
        >>> print(f"Explanation: {risk.explanation.summary}")
    """
    
    def __init__(
        self,
        config: Optional[RiskEngineConfig] = None,
        zone_manager: Optional[ZoneManager] = None
    ):
        """
        Initialize the risk engine.
        
        Args:
            config: Engine configuration
            zone_manager: Zone manager instance (creates new if not provided)
        """
        self._config = config or RiskEngineConfig()
        self._zone_manager = zone_manager or ZoneManager()
        self._temporal_model = TemporalRiskModel(self._config.temporal)
        
        logger.info(
            f"RiskEngine initialized with "
            f"use_zones={self._config.use_zones}, "
            f"use_temporal={self._config.use_temporal}"
        )
    
    @property
    def config(self) -> RiskEngineConfig:
        """Get engine configuration."""
        return self._config
    
    @property
    def zone_manager(self) -> ZoneManager:
        """Get zone manager."""
        return self._zone_manager
    
    @property
    def temporal_model(self) -> TemporalRiskModel:
        """Get temporal model."""
        return self._temporal_model
    
    def compute_risk(
        self,
        track: TrackAnalysis,
        crowd_metrics: CrowdMetrics,
        frame_id: int,
        timestamp: float
    ) -> RiskScore:
        """
        Compute risk score for a single track.
        
        Args:
            track: Track analysis with behavior flags
            crowd_metrics: Frame-level crowd metrics
            frame_id: Current frame number
            timestamp: Current timestamp
            
        Returns:
            RiskScore with score, level, and explanation
        """
        factors: List[RiskFactor] = []
        weights = self._config.weights
        behavior = track.behavior
        
        # ═══════════════════════════════════════════════════════════════
        # SIGNAL EXTRACTION
        # ═══════════════════════════════════════════════════════════════
        
        # 1. Loitering
        loitering_value = self._compute_loitering_signal(behavior, track.time_tracked)
        factors.append(RiskFactor(
            name="loitering",
            display_name="Prolonged Loitering" if loitering_value > 0.5 else "Stationary",
            weight=weights.loitering,
            raw_value=loitering_value,
            weighted_value=loitering_value * weights.loitering,
            description=f"Tracked for {track.time_tracked:.1f}s"
        ))
        
        # 2. Speed Anomaly
        speed_value = 1.0 if behavior.sudden_speed_change else 0.0
        factors.append(RiskFactor(
            name="speed_anomaly",
            display_name="Sudden Speed Change",
            weight=weights.speed_anomaly,
            raw_value=speed_value,
            weighted_value=speed_value * weights.speed_anomaly,
            description="Rapid speed change detected"
        ))
        
        # 3. Direction Change
        direction_value = 1.0 if behavior.direction_reversal else 0.0
        factors.append(RiskFactor(
            name="direction_change",
            display_name="Direction Reversal",
            weight=weights.direction_change,
            raw_value=direction_value,
            weighted_value=direction_value * weights.direction_change,
            description="Sudden direction reversal"
        ))
        
        # 4. Crowd Density
        crowd_value = min(
            crowd_metrics.max_density / self._config.normalize_crowd_at,
            1.0
        ) if crowd_metrics.crowd_detected else 0.0
        factors.append(RiskFactor(
            name="crowd_density",
            display_name="High Crowd Density",
            weight=weights.crowd_density,
            raw_value=crowd_value,
            weighted_value=crowd_value * weights.crowd_density,
            description=f"Density: {crowd_metrics.max_density}"
        ))
        
        # 5. Erratic Motion
        erratic_value = 1.0 if behavior.is_erratic else 0.0
        factors.append(RiskFactor(
            name="erratic_motion",
            display_name="Erratic Movement",
            weight=weights.erratic_motion,
            raw_value=erratic_value,
            weighted_value=erratic_value * weights.erratic_motion,
            description="Unpredictable movement pattern"
        ))
        
        # 6. Running (persons only)
        running_value = 1.0 if behavior.is_running else 0.0
        factors.append(RiskFactor(
            name="running",
            display_name="Running",
            weight=weights.running,
            raw_value=running_value,
            weighted_value=running_value * weights.running,
            description="Person running"
        ))
        
        # ═══════════════════════════════════════════════════════════════
        # BASE SCORE COMPUTATION
        # ═══════════════════════════════════════════════════════════════
        
        base_score = sum(f.weighted_value for f in factors)
        
        # ═══════════════════════════════════════════════════════════════
        # ZONE CONTEXT
        # ═══════════════════════════════════════════════════════════════
        
        zone_multiplier = 1.0
        zone_context = ZoneContext()
        
        if self._config.use_zones:
            zone_context = self._zone_manager.get_context(bbox=track.current_bbox)
            zone_multiplier = zone_context.multiplier
            
            # Add zone as a factor
            zone_value = (zone_multiplier - 1.0) / 1.0  # Normalize 1.0-2.0 to 0.0-1.0
            factors.append(RiskFactor(
                name="zone_context",
                display_name=f"Zone: {zone_context.zone_name}",
                weight=weights.zone_context,
                raw_value=zone_value,
                weighted_value=zone_value * weights.zone_context,
                description=f"Multiplier: {zone_multiplier:.1f}x"
            ))
        
        zone_adjusted = base_score * zone_multiplier
        
        # ═══════════════════════════════════════════════════════════════
        # TEMPORAL ADJUSTMENT
        # ═══════════════════════════════════════════════════════════════
        
        temporal_adjustment = 0.0
        
        if self._config.use_temporal:
            # Determine if behavior is suspicious
            is_suspicious = behavior.has_anomaly or behavior.is_loitering
            
            # Update temporal model
            temporal_state = self._temporal_model.update(
                track.track_id, is_suspicious, frame_id
            )
            temporal_adjustment = temporal_state.adjustment
        
        # ═══════════════════════════════════════════════════════════════
        # FINAL SCORE
        # ═══════════════════════════════════════════════════════════════
        
        final_score = min(zone_adjusted + temporal_adjustment, 1.0)
        final_score = max(final_score, 0.0)
        
        # Determine risk level
        risk_level = RiskLevel.from_score(final_score, self._config.thresholds)
        
        # Generate explanation
        explanation = self._generate_explanation(
            track, factors, zone_context, final_score, risk_level
        )
        
        return RiskScore(
            track_id=track.track_id,
            score=final_score,
            level=risk_level,
            explanation=explanation,
            zone_multiplier=zone_multiplier,
            temporal_adjustment=temporal_adjustment,
            base_score=base_score,
            timestamp=timestamp
        )
    
    def compute_frame_risks(
        self,
        track_analyses: List[TrackAnalysis],
        crowd_metrics: CrowdMetrics,
        frame_id: int,
        timestamp: float
    ) -> FrameRiskSummary:
        """
        Compute risk scores for all tracks in a frame.
        
        Args:
            track_analyses: List of track analyses
            crowd_metrics: Frame-level crowd metrics
            frame_id: Current frame number
            timestamp: Current timestamp
            
        Returns:
            FrameRiskSummary with all track risks
        """
        track_risks = []
        max_score = 0.0
        max_level = RiskLevel.LOW
        concerning = 0
        
        for track in track_analyses:
            risk = self.compute_risk(track, crowd_metrics, frame_id, timestamp)
            track_risks.append(risk)
            
            if risk.score > max_score:
                max_score = risk.score
                max_level = risk.level
            
            if risk.is_concerning:
                concerning += 1
        
        # Cleanup stale temporal states periodically
        if frame_id % 60 == 0:
            self._temporal_model.cleanup_stale_tracks(frame_id)
        
        return FrameRiskSummary(
            frame_id=frame_id,
            timestamp=timestamp,
            track_risks=track_risks,
            max_risk_score=max_score,
            max_risk_level=max_level,
            concerning_tracks=concerning,
            total_tracks=len(track_risks)
        )
    
    def _compute_loitering_signal(
        self,
        behavior: BehaviorFlags,
        time_tracked: float
    ) -> float:
        """
        Compute loitering signal value.
        
        Args:
            behavior: Behavior flags
            time_tracked: Time tracked in seconds
            
        Returns:
            Signal value between 0.0 and 1.0
        """
        if not behavior.is_loitering and not behavior.is_stationary:
            return 0.0
        
        if behavior.is_loitering:
            # Full loitering: scale by duration (max at 30s)
            return min(time_tracked / 30.0, 1.0)
        elif behavior.is_stationary:
            # Just stationary: lower value
            return min(time_tracked / 60.0, 0.5)
        
        return 0.0
    
    def _generate_explanation(
        self,
        track: TrackAnalysis,
        factors: List[RiskFactor],
        zone_context: ZoneContext,
        score: float,
        level: RiskLevel
    ) -> RiskExplanation:
        """
        Generate human-readable explanation.
        
        Args:
            track: Track analysis
            factors: Contributing factors
            zone_context: Zone context
            score: Final risk score
            level: Risk level
            
        Returns:
            RiskExplanation with summary and details
        """
        # Get significant factors
        significant = [f for f in factors if f.weighted_value > 0.02]
        significant.sort(key=lambda f: f.weighted_value, reverse=True)
        
        # Build summary
        parts = []
        parts.append(f"{track.class_name}")
        
        if track.behavior.is_loitering:
            parts.append(f"loitering for {track.time_tracked:.0f}s")
        
        if zone_context.in_zone and zone_context.zone_type != ZoneType.NORMAL:
            parts.append(f"in {zone_context.zone_name.lower()}")
        
        if track.behavior.direction_reversal:
            parts.append("with direction reversal")
        
        if track.behavior.sudden_speed_change:
            parts.append("with sudden speed change")
        
        if track.behavior.is_erratic:
            parts.append("showing erratic motion")
        
        summary = " ".join(parts)
        
        # Add recommendations based on level
        recommendations = []
        if level == RiskLevel.CRITICAL:
            recommendations.append("Immediate attention required")
        elif level == RiskLevel.HIGH:
            recommendations.append("Alert recommended")
        elif level == RiskLevel.MEDIUM:
            recommendations.append("Continue monitoring")
        
        return RiskExplanation(
            summary=summary,
            factors=significant,
            recommendations=recommendations
        )
    
    def reset(self) -> None:
        """Reset engine state."""
        self._temporal_model.reset()
        logger.info("RiskEngine reset")
    
    def __repr__(self) -> str:
        return (
            f"RiskEngine(use_zones={self._config.use_zones}, "
            f"use_temporal={self._config.use_temporal})"
        )
