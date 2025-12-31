"""
AegisAI - Semantic Trigger Unit Tests

Tests for semantic trigger logic ensuring DINO is only
invoked under correct conditions.
"""

import pytest
import numpy as np
from unittest.mock import MagicMock, patch

from aegis.semantic.semantic_trigger import (
    SemanticTrigger,
    TriggerEvent,
    TriggerType
)


class TestSemanticTrigger:
    """Tests for SemanticTrigger class."""
    
    @pytest.fixture
    def config(self):
        """Create test config."""
        config = MagicMock()
        config.risk_threshold_trigger = 0.6
        return config
    
    @pytest.fixture
    def trigger(self, config):
        """Create trigger instance."""
        return SemanticTrigger(config)
    
    @pytest.fixture
    def sample_frame(self):
        """Create sample frame."""
        return np.zeros((480, 640, 3), dtype=np.uint8)
    
    @pytest.fixture
    def sample_track(self):
        """Create sample track analysis."""
        track = MagicMock()
        track.track_id = 1
        track.class_name = "Person"
        track.current_bbox = (100, 100, 200, 300)
        track.behavior = MagicMock()
        track.behavior.is_loitering = False
        track.behavior.sudden_speed_change = False
        track.behavior.direction_reversal = False
        track.behavior.is_erratic = False
        return track
    
    @pytest.fixture
    def risk_summary(self):
        """Create sample risk summary."""
        risk = MagicMock()
        risk.track_risks = []
        return risk
    
    def test_trigger_creation(self, trigger, config):
        """Trigger should be created with config."""
        assert trigger is not None
        assert trigger._config == config
    
    def test_no_triggers_on_normal_behavior(
        self, trigger, sample_track, risk_summary, sample_frame
    ):
        """Normal tracks should not trigger DINO."""
        events = trigger.check_triggers(
            tracks=[sample_track],
            risk_scores=risk_summary,
            user_query=None,
            frame=sample_frame
        )
        
        assert len(events) == 0
    
    def test_user_query_triggers(
        self, trigger, sample_track, risk_summary, sample_frame
    ):
        """User query should trigger DINO for all tracks."""
        events = trigger.check_triggers(
            tracks=[sample_track],
            risk_scores=risk_summary,
            user_query="person with bag",
            frame=sample_frame
        )
        
        assert len(events) == 1
        assert events[0].trigger_type == TriggerType.USER_QUERY
        assert events[0].prompt == "person with bag"
        assert events[0].track_id == 1
    
    def test_risk_threshold_triggers(
        self, trigger, sample_track, sample_frame
    ):
        """High risk score should trigger DINO."""
        # Create risk summary with high risk track
        risk = MagicMock()
        risk.score = 0.75  # Above 0.6 threshold
        risk.track_id = 1
        
        risk_summary = MagicMock()
        risk_summary.track_risks = [risk]
        
        events = trigger.check_triggers(
            tracks=[sample_track],
            risk_scores=risk_summary,
            user_query=None,
            frame=sample_frame
        )
        
        assert len(events) == 1
        assert events[0].trigger_type == TriggerType.RISK_THRESHOLD
    
    def test_loitering_triggers(
        self, trigger, sample_track, risk_summary, sample_frame
    ):
        """Loitering behavior should trigger DINO."""
        sample_track.behavior.is_loitering = True
        
        events = trigger.check_triggers(
            tracks=[sample_track],
            risk_scores=risk_summary,
            user_query=None,
            frame=sample_frame
        )
        
        assert len(events) == 1
        assert events[0].trigger_type == TriggerType.BEHAVIOR_CHANGE
    
    def test_cooldown_prevents_rapid_triggers(
        self, trigger, sample_track, risk_summary, sample_frame
    ):
        """Same track should not trigger multiple times rapidly."""
        sample_track.behavior.is_loitering = True
        
        # First trigger
        events1 = trigger.check_triggers(
            tracks=[sample_track],
            risk_scores=risk_summary,
            user_query=None,
            frame=sample_frame
        )
        
        # Second trigger immediately after (should be blocked)
        events2 = trigger.check_triggers(
            tracks=[sample_track],
            risk_scores=risk_summary,
            user_query=None,
            frame=sample_frame
        )
        
        assert len(events1) == 1
        assert len(events2) == 0  # Blocked by cooldown
    
    def test_no_triggers_without_frame(
        self, trigger, sample_track, risk_summary
    ):
        """No triggers should occur without a frame."""
        events = trigger.check_triggers(
            tracks=[sample_track],
            risk_scores=risk_summary,
            user_query="test query",
            frame=None
        )
        
        assert len(events) == 0
    
    def test_user_query_has_highest_priority(
        self, trigger, sample_track, sample_frame
    ):
        """User query should have higher priority than behavior."""
        sample_track.behavior.is_loitering = True
        
        risk = MagicMock()
        risk.score = 0.75
        risk.track_id = 1
        risk_summary = MagicMock()
        risk_summary.track_risks = [risk]
        
        events = trigger.check_triggers(
            tracks=[sample_track],
            risk_scores=risk_summary,
            user_query="test query",
            frame=sample_frame
        )
        
        # With user query, should use user query trigger (highest priority)
        assert len(events) == 1
        assert events[0].trigger_type == TriggerType.USER_QUERY
