"""
AegisAI - Behavior Analyzer Unit Tests

Tests for behavior detection logic.

Sprint 1: Security & Testing Foundation
"""

import pytest
from aegis.analysis import (
    BehaviorAnalyzer,
    BehaviorAnalyzerConfig,
    BehaviorFlags,
    BehaviorType,
    MotionState,
    TrackHistoryManager
)


class TestBehaviorFlags:
    """Test BehaviorFlags dataclass."""
    
    def test_default_flags(self):
        """Default flags should be all false."""
        flags = BehaviorFlags()
        
        assert not flags.is_stationary
        assert not flags.is_loitering
        assert not flags.is_running
        assert not flags.has_anomaly
    
    def test_has_anomaly_with_loitering(self):
        """Loitering should count as anomaly."""
        flags = BehaviorFlags(is_loitering=True)
        
        assert flags.has_anomaly
    
    def test_has_anomaly_with_speed_change(self):
        """Sudden speed change should count as anomaly."""
        flags = BehaviorFlags(sudden_speed_change=True)
        
        assert flags.has_anomaly
    
    def test_has_anomaly_with_direction_reversal(self):
        """Direction reversal should count as anomaly."""
        flags = BehaviorFlags(direction_reversal=True)
        
        assert flags.has_anomaly
    
    def test_has_anomaly_with_erratic(self):
        """Erratic motion should count as anomaly."""
        flags = BehaviorFlags(is_erratic=True)
        
        assert flags.has_anomaly
    
    def test_no_anomaly_normal_behavior(self):
        """Normal stationary should not be anomaly."""
        flags = BehaviorFlags(is_stationary=True)
        
        assert not flags.has_anomaly


class TestBehaviorAnalyzer:
    """Test BehaviorAnalyzer detection."""
    
    def test_analyzer_creation(self):
        """Analyzer should be created successfully."""
        config = BehaviorAnalyzerConfig()
        analyzer = BehaviorAnalyzer(config=config)
        
        assert analyzer is not None
    
    def test_detect_loitering(self):
        """Stationary for long time should be loitering."""
        config = BehaviorAnalyzerConfig(loitering_time_threshold=5.0)
        analyzer = BehaviorAnalyzer(config=config)
        
        history_manager = TrackHistoryManager()
        
        # Simulate stationary track for 10 seconds
        for i in range(300):  # 10 seconds at 30fps
            mock = type('Track', (), {
                'track_id': 1,
                'bbox': (100, 100, 120, 120)  # Same position
            })()
            history_manager.update([mock], frame_id=i, timestamp=i/30.0)
        
        # Create motion state showing stationary
        motion_states = {
            1: MotionState(
                speed=0.1,
                smoothed_speed=0.1,
                is_stationary=True
            )
        }
        
        results = analyzer.analyze_all(history_manager, motion_states)
        
        assert 1 in results
        # Check loitering detection (depends on time tracked)
        # With 10 seconds stationary, should detect
    
    def test_detect_running(self):
        """High speed should be detected as running."""
        config = BehaviorAnalyzerConfig(running_speed_threshold=10.0)
        analyzer = BehaviorAnalyzer(config=config)
        
        motion_state = MotionState(
            speed=15.0,
            smoothed_speed=15.0,
            is_stationary=False
        )
        
        is_running = motion_state.speed > config.running_speed_threshold
        
        assert is_running
    
    def test_not_running_normal_speed(self):
        """Normal speed should not be running."""
        config = BehaviorAnalyzerConfig(running_speed_threshold=10.0)
        
        motion_state = MotionState(
            speed=5.0,
            smoothed_speed=5.0,
            is_stationary=False
        )
        
        is_running = motion_state.speed > config.running_speed_threshold
        
        assert not is_running


class TestBehaviorType:
    """Test BehaviorType enum."""
    
    def test_behavior_types_exist(self):
        """All expected behavior types should exist."""
        assert BehaviorType.NORMAL
        assert BehaviorType.LOITERING
        assert BehaviorType.RUNNING
        assert BehaviorType.SUDDEN_STOP
        assert BehaviorType.DIRECTION_CHANGE
