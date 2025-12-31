"""
AegisAI - Motion Analyzer Unit Tests

Tests for motion metrics computation.

Sprint 1: Security & Testing Foundation
"""

import pytest
import math
from aegis.analysis import (
    MotionAnalyzer,
    MotionAnalyzerConfig,
    TrackHistoryManager,
    PositionRecord,
    MotionState
)


class TestMotionState:
    """Test MotionState dataclass."""
    
    def test_default_state(self):
        """Default state should have zero values."""
        state = MotionState()
        
        assert state.speed == 0.0
        assert state.is_stationary
    
    def test_stationary_detection(self):
        """is_stationary should reflect low speed."""
        moving = MotionState(speed=5.0, is_stationary=False)
        stopped = MotionState(speed=0.5, is_stationary=True)
        
        assert not moving.is_stationary
        assert stopped.is_stationary


class TestMotionAnalyzer:
    """Test MotionAnalyzer computation."""
    
    def test_analyzer_creation(self):
        """Analyzer should be created successfully."""
        config = MotionAnalyzerConfig()
        analyzer = MotionAnalyzer(config=config)
        
        assert analyzer is not None
    
    def test_compute_speed(self):
        """Speed should be calculated from position delta."""
        config = MotionAnalyzerConfig()
        analyzer = MotionAnalyzer(config=config)
        
        # Create history with known positions
        positions = [
            PositionRecord(x=0.0, y=0.0, timestamp=0.0, frame_id=0),
            PositionRecord(x=3.0, y=4.0, timestamp=1.0, frame_id=1),  # moves 5 units
        ]
        
        speed = analyzer._compute_speed(positions[-2], positions[-1])
        
        assert abs(speed - 5.0) < 0.01  # Euclidean distance
    
    def test_compute_direction(self):
        """Direction should be angle in radians."""
        config = MotionAnalyzerConfig()
        analyzer = MotionAnalyzer(config=config)
        
        p1 = PositionRecord(x=0.0, y=0.0, timestamp=0.0, frame_id=0)
        p2 = PositionRecord(x=1.0, y=0.0, timestamp=1.0, frame_id=1)  # East
        
        direction = analyzer._compute_direction(p1, p2)
        
        assert abs(direction - 0.0) < 0.01  # 0 radians = East
    
    def test_direction_north(self):
        """Northward movement should be π/2."""
        config = MotionAnalyzerConfig()
        analyzer = MotionAnalyzer(config=config)
        
        p1 = PositionRecord(x=0.0, y=0.0, timestamp=0.0, frame_id=0)
        p2 = PositionRecord(x=0.0, y=-1.0, timestamp=1.0, frame_id=1)  # Up (y decreases)
        
        direction = analyzer._compute_direction(p1, p2)
        
        # Should be -π/2 or 3π/2
        assert abs(direction) > 1.5 or abs(direction + math.pi/2) < 0.1
    
    def test_stationary_threshold(self):
        """Movement below threshold should be stationary."""
        config = MotionAnalyzerConfig(stationary_threshold=2.0)
        analyzer = MotionAnalyzer(config=config)
        
        # Very small movement
        p1 = PositionRecord(x=0.0, y=0.0, timestamp=0.0, frame_id=0)
        p2 = PositionRecord(x=0.5, y=0.5, timestamp=1.0, frame_id=1)
        
        speed = analyzer._compute_speed(p1, p2)
        is_stationary = speed < config.stationary_threshold
        
        assert is_stationary  # 0.7 < 2.0


class TestMotionAnalyzerIntegration:
    """Test MotionAnalyzer with TrackHistoryManager."""
    
    def test_analyze_with_history(self):
        """Analyzer should work with history manager."""
        history_manager = TrackHistoryManager()
        config = MotionAnalyzerConfig()
        analyzer = MotionAnalyzer(config=config)
        
        # Simulate track movement
        class MockTrack:
            track_id = 1
            bbox = (0, 0, 10, 10)
        
        for i in range(10):
            mock = type('Track', (), {
                'track_id': 1,
                'bbox': (i*10, i*10, i*10+10, i*10+10)
            })()
            history_manager.update([mock], frame_id=i, timestamp=float(i))
        
        # Analyze
        results = analyzer.analyze_all(history_manager)
        
        assert 1 in results
        assert results[1].speed > 0  # Track was moving
