"""
AegisAI - Risk Engine Unit Tests

Tests for risk score calculation, level mapping, and explainability.

Sprint 1: Security & Testing Foundation
"""

import pytest
from aegis.risk import (
    RiskEngine,
    RiskEngineConfig,
    RiskWeights,
    RiskThresholds,
    TemporalConfig,
    RiskLevel
)
from aegis.analysis import (
    TrackAnalysis,
    MotionState,
    BehaviorFlags,
    CrowdMetrics
)


class TestRiskLevel:
    """Test RiskLevel enum and score mapping."""
    
    def test_low_score_maps_to_low(self):
        """Scores below 0.25 should be LOW."""
        assert RiskLevel.from_score(0.0).value == "LOW"
        assert RiskLevel.from_score(0.1).value == "LOW"
        assert RiskLevel.from_score(0.24).value == "LOW"
    
    def test_medium_score_maps_to_medium(self):
        """Scores 0.25-0.49 should be MEDIUM."""
        assert RiskLevel.from_score(0.25).value == "MEDIUM"
        assert RiskLevel.from_score(0.35).value == "MEDIUM"
        assert RiskLevel.from_score(0.49).value == "MEDIUM"
    
    def test_high_score_maps_to_high(self):
        """Scores 0.50-0.74 should be HIGH."""
        assert RiskLevel.from_score(0.50).value == "HIGH"
        assert RiskLevel.from_score(0.60).value == "HIGH"
        assert RiskLevel.from_score(0.74).value == "HIGH"
    
    def test_critical_score_maps_to_critical(self):
        """Scores 0.75+ should be CRITICAL."""
        assert RiskLevel.from_score(0.75).value == "CRITICAL"
        assert RiskLevel.from_score(0.90).value == "CRITICAL"
        assert RiskLevel.from_score(1.0).value == "CRITICAL"


class TestRiskEngine:
    """Test RiskEngine scoring logic."""
    
    def test_engine_creation(self, risk_engine):
        """Engine should be created successfully."""
        assert risk_engine is not None
    
    def test_normal_behavior_low_risk(self, risk_engine, crowd_metrics):
        """Normal behavior should produce low risk."""
        # Create track with no anomalies
        track = TrackAnalysis(
            track_id=1,
            class_id=0,
            class_name="Person",
            motion=MotionState(
                speed=2.0,
                smoothed_speed=2.0,
                velocity=(1.5, 1.0),
                direction=0.5,
                acceleration=0.0,
                is_stationary=False
            ),
            behavior=BehaviorFlags(
                is_stationary=False,
                is_loitering=False,
                is_running=False,
                sudden_speed_change=False,
                direction_reversal=False,
                is_erratic=False
            ),
            history_length=30,
            time_tracked=2.0,
            current_position=(150.0, 150.0),
            current_bbox=(100, 100, 200, 200)
        )
        
        risk = risk_engine.compute_risk(
            track=track,
            crowd_metrics=crowd_metrics,
            frame_id=1,
            timestamp=1.0
        )
        
        assert risk.score < 0.25
        assert risk.level == RiskLevel.LOW
    
    def test_loitering_increases_risk(self, risk_engine, crowd_metrics):
        """Loitering behavior should increase risk score."""
        # Create track with loitering
        track = TrackAnalysis(
            track_id=2,
            class_id=0,
            class_name="Person",
            motion=MotionState(
                speed=0.5,
                smoothed_speed=0.5,
                velocity=(0.0, 0.0),
                direction=0.0,
                acceleration=0.0,
                is_stationary=True
            ),
            behavior=BehaviorFlags(
                is_stationary=True,
                is_loitering=True,
                is_running=False,
                sudden_speed_change=False,
                direction_reversal=False,
                is_erratic=False,
                stationary_duration=30.0
            ),
            history_length=60,
            time_tracked=30.0,
            current_position=(150.0, 150.0),
            current_bbox=(100, 100, 200, 200)
        )
        
        risk = risk_engine.compute_risk(
            track=track,
            crowd_metrics=crowd_metrics,
            frame_id=1,
            timestamp=30.0
        )
        
        assert risk.score >= 0.20  # Loitering should contribute
        assert "loitering" in risk.explanation.summary.lower() or len(risk.explanation.factors) > 0
    
    def test_multiple_anomalies_compound(self, risk_engine, crowd_metrics):
        """Multiple anomalies should compound risk."""
        # Create track with multiple concerning behaviors
        track = TrackAnalysis(
            track_id=3,
            class_id=0,
            class_name="Person",
            motion=MotionState(
                speed=15.0,
                smoothed_speed=10.0,
                velocity=(10.0, 5.0),
                direction=1.5,
                acceleration=5.0,
                is_stationary=False
            ),
            behavior=BehaviorFlags(
                is_stationary=False,
                is_loitering=False,
                is_running=True,
                sudden_speed_change=True,
                direction_reversal=True,
                is_erratic=True,
                direction_variance=2.0
            ),
            history_length=60,
            time_tracked=5.0,
            current_position=(150.0, 150.0),
            current_bbox=(100, 100, 200, 200)
        )
        
        risk = risk_engine.compute_risk(
            track=track,
            crowd_metrics=crowd_metrics,
            frame_id=1,
            timestamp=5.0
        )
        
        assert risk.score >= 0.40  # Multiple anomalies should compound
    
    def test_risk_score_bounded(self, risk_engine, crowd_metrics, track_analysis):
        """Risk score should always be between 0 and 1."""
        risk = risk_engine.compute_risk(
            track=track_analysis,
            crowd_metrics=crowd_metrics,
            frame_id=1,
            timestamp=1.0
        )
        
        assert 0.0 <= risk.score <= 1.0
    
    def test_explanation_always_present(self, risk_engine, crowd_metrics, track_analysis):
        """Every risk score should have an explanation."""
        risk = risk_engine.compute_risk(
            track=track_analysis,
            crowd_metrics=crowd_metrics,
            frame_id=1,
            timestamp=1.0
        )
        
        assert risk.explanation is not None
        assert risk.explanation.summary is not None
        assert len(risk.explanation.summary) > 0
    
    def test_frame_risks_computation(self, risk_engine, track_analysis, crowd_metrics):
        """Frame risk summary should include all tracks."""
        tracks = [track_analysis]
        
        summary = risk_engine.compute_frame_risks(
            track_analyses=tracks,
            crowd_metrics=crowd_metrics,
            frame_id=1,
            timestamp=1.0
        )
        
        assert summary is not None
        assert len(summary.track_risks) == 1
        assert summary.max_risk_score >= 0.0


class TestRiskDeterminism:
    """Test that risk scoring is deterministic."""
    
    def test_same_input_same_output(self, risk_engine, track_analysis, crowd_metrics):
        """Same inputs should produce same risk score."""
        risk1 = risk_engine.compute_risk(
            track=track_analysis,
            crowd_metrics=crowd_metrics,
            frame_id=1,
            timestamp=1.0
        )
        
        risk2 = risk_engine.compute_risk(
            track=track_analysis,
            crowd_metrics=crowd_metrics,
            frame_id=1,
            timestamp=1.0
        )
        
        assert risk1.score == risk2.score
        assert risk1.level == risk2.level
