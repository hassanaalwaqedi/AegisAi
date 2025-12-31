"""
AegisAI - Pipeline Integration Tests

Tests for end-to-end pipeline data flow.

Sprint 1: Security & Testing Foundation
"""

import pytest
from aegis.analysis import (
    TrackHistoryManager,
    MotionAnalyzer,
    MotionAnalyzerConfig,
    BehaviorAnalyzer,
    BehaviorAnalyzerConfig,
    CrowdAnalyzer,
    CrowdAnalyzerConfig,
    TrackAnalysis
)
from aegis.risk import (
    RiskEngine,
    RiskEngineConfig,
    RiskWeights,
    RiskThresholds,
    TemporalConfig
)
from aegis.alerts import (
    AlertManager,
    AlertManagerConfig,
    AlertLevel
)


class MockTrack:
    """Mock track for testing."""
    def __init__(self, track_id, x, y, width=20, height=40):
        self.track_id = track_id
        self.class_id = 0
        self.class_name = "Person"
        self.bbox = (x, y, x + width, y + height)
        self.confidence = 0.95


class TestPipelineFlow:
    """Test complete pipeline data flow."""
    
    def test_detection_to_analysis(self):
        """Tracks should flow from detection to analysis."""
        history_manager = TrackHistoryManager()
        motion_analyzer = MotionAnalyzer()
        
        # Simulate multiple frames of tracking
        for frame_id in range(30):
            tracks = [
                MockTrack(1, 100 + frame_id*2, 100),
                MockTrack(2, 200, 200)  # Stationary
            ]
            history_manager.update(tracks, frame_id=frame_id, timestamp=frame_id/30.0)
        
        # Analyze motion
        motion_states = motion_analyzer.analyze_all(history_manager)
        
        assert 1 in motion_states
        assert 2 in motion_states
        assert motion_states[1].speed > motion_states[2].speed  # Track 1 was moving
    
    def test_analysis_to_risk(self):
        """Analysis results should flow to risk engine."""
        # Setup analysis
        history_manager = TrackHistoryManager()
        motion_analyzer = MotionAnalyzer()
        behavior_analyzer = BehaviorAnalyzer()
        crowd_analyzer = CrowdAnalyzer()
        
        # Setup risk engine
        risk_engine = RiskEngine(
            config=RiskEngineConfig(
                use_zones=False,
                use_temporal=False
            )
        )
        
        # Simulate stationary track (potential loiterer)
        for frame_id in range(180):  # 6 seconds at 30fps
            tracks = [MockTrack(1, 100, 100)]
            history_manager.update(tracks, frame_id=frame_id, timestamp=frame_id/30.0)
        
        # Run analysis pipeline
        motion_states = motion_analyzer.analyze_all(history_manager)
        behaviors = behavior_analyzer.analyze_all(history_manager, motion_states)
        
        frame_shape = (720, 1280, 3)
        tracks = [MockTrack(1, 100, 100)]
        crowd_metrics = crowd_analyzer.analyze(tracks, frame_shape)
        
        # Build track analysis
        history = history_manager.get_history(1)
        track_analysis = TrackAnalysis(
            track_id=1,
            class_id=0,
            class_name="Person",
            motion=motion_states.get(1, motion_analyzer.analyze(history)),
            behavior=behaviors.get(1),
            history_length=history.history_length,
            time_tracked=history.duration,
            current_position=(100.0, 100.0),
            current_bbox=(100, 100, 120, 140)
        )
        
        # Compute risk
        risk = risk_engine.compute_risk(
            track=track_analysis,
            crowd_metrics=crowd_metrics,
            frame_id=179,
            timestamp=6.0
        )
        
        assert risk is not None
        assert risk.explanation is not None
    
    def test_risk_to_alerts(self):
        """High risk scores should generate alerts."""
        alert_manager = AlertManager(
            config=AlertManagerConfig(
                enabled=True,
                min_level=AlertLevel.HIGH,
                cooldown_seconds=0.1
            )
        )
        
        # Simulate high risk event
        alert = alert_manager.process_risk(
            track_id=1,
            risk_level="HIGH",
            risk_score=0.65,
            message="Test integration alert",
            zone="Test Zone",
            factors=["Loitering", "Restricted Area"]
        )
        
        assert alert is not None
        assert alert.track_id == 1
        assert alert.level == AlertLevel.HIGH
    
    def test_full_pipeline_integration(self):
        """Complete pipeline should process without errors."""
        # All components
        history_manager = TrackHistoryManager()
        motion_analyzer = MotionAnalyzer()
        behavior_analyzer = BehaviorAnalyzer()
        crowd_analyzer = CrowdAnalyzer()
        risk_engine = RiskEngine()
        alert_manager = AlertManager(
            config=AlertManagerConfig(
                enabled=True,
                min_level=AlertLevel.HIGH,
                cooldown_seconds=0.1,
                log_to_file=False
            )
        )
        
        frame_shape = (720, 1280, 3)
        alerts_generated = 0
        
        # Simulate 5 seconds of video
        for frame_id in range(150):
            # Create tracks (one moving, one loitering)
            tracks = [
                MockTrack(1, 100 + frame_id, 100),      # Moving
                MockTrack(2, 500, 300),                  # Stationary
            ]
            
            # Update history
            history_manager.update(tracks, frame_id=frame_id, timestamp=frame_id/30.0)
            
            # Analyze every 10 frames
            if frame_id % 10 == 0 and frame_id > 30:
                motion_states = motion_analyzer.analyze_all(history_manager)
                behaviors = behavior_analyzer.analyze_all(history_manager, motion_states)
                crowd_metrics = crowd_analyzer.analyze(tracks, frame_shape)
                
                # Process each track
                for track in tracks:
                    history = history_manager.get_history(track.track_id)
                    if not history:
                        continue
                    
                    motion = motion_states.get(track.track_id)
                    behavior = behaviors.get(track.track_id)
                    
                    if motion and behavior:
                        bbox = track.bbox
                        track_analysis = TrackAnalysis(
                            track_id=track.track_id,
                            class_id=track.class_id,
                            class_name=track.class_name,
                            motion=motion,
                            behavior=behavior,
                            history_length=history.history_length,
                            time_tracked=history.duration,
                            current_position=(
                                (bbox[0] + bbox[2]) / 2,
                                (bbox[1] + bbox[3]) / 2
                            ),
                            current_bbox=bbox
                        )
                        
                        risk = risk_engine.compute_risk(
                            track=track_analysis,
                            crowd_metrics=crowd_metrics,
                            frame_id=frame_id,
                            timestamp=frame_id/30.0
                        )
                        
                        if risk.is_concerning:
                            alert = alert_manager.process_risk(
                                track_id=risk.track_id,
                                risk_level=risk.level.value,
                                risk_score=risk.score,
                                message=risk.explanation.summary
                            )
                            if alert:
                                alerts_generated += 1
        
        # Pipeline should complete without error
        assert history_manager.track_count >= 2
        # Alerts may or may not be generated depending on thresholds
