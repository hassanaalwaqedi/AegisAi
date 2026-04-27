"""
AegisAI - Edge Risk Filter Unit Tests

Tests the edge-side risk assessment logic including
weapon detection scoring, bbox overlap, cooldowns, and event creation.
"""

import time
import numpy as np
import pytest
from unittest.mock import MagicMock
from collections import namedtuple

from aegis.edge.edge_risk_filter import EdgeRiskFilter, bbox_iou, bbox_contains
from aegis.edge.event_types import EdgeAssessment, TrackSummary, SuspiciousEvent
from config import EdgeConfig


# ── Helper: Mock Track ──

MockTrack = namedtuple('MockTrack', [
    'track_id', 'bbox', 'class_name', 'class_id', 'confidence',
    'is_weapon', 'is_person', 'is_animal', 'object_category'
])


def make_person(track_id=1, bbox=(100, 100, 300, 400)):
    return MockTrack(
        track_id=track_id, bbox=bbox, class_name="Person",
        class_id=0, confidence=0.9,
        is_weapon=False, is_person=True, is_animal=False,
        object_category="person"
    )


def make_weapon(track_id=10, bbox=(150, 200, 200, 250), class_name="Gun"):
    return MockTrack(
        track_id=track_id, bbox=bbox, class_name=class_name,
        class_id=100, confidence=0.8,
        is_weapon=True, is_person=False, is_animal=False,
        object_category="weapon"
    )


def make_animal(track_id=20, bbox=(400, 400, 500, 500)):
    return MockTrack(
        track_id=track_id, bbox=bbox, class_name="Dog",
        class_id=16, confidence=0.7,
        is_weapon=False, is_person=False, is_animal=True,
        object_category="animal"
    )


# ── Tests: bbox_iou ──

class TestBboxIoU:
    def test_no_overlap(self):
        assert bbox_iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    
    def test_full_overlap(self):
        assert bbox_iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    
    def test_partial_overlap(self):
        iou = bbox_iou((0, 0, 10, 10), (5, 5, 15, 15))
        assert 0.1 < iou < 0.2  # ~14.3%
    
    def test_zero_area(self):
        assert bbox_iou((0, 0, 0, 0), (0, 0, 10, 10)) == 0.0


class TestBboxContains:
    def test_contained(self):
        assert bbox_contains((0, 0, 100, 100), (40, 40, 60, 60)) is True
    
    def test_not_contained(self):
        assert bbox_contains((0, 0, 100, 100), (200, 200, 300, 300)) is False


# ── Tests: EdgeRiskFilter ──

class TestEdgeRiskFilter:
    def setup_method(self):
        config = EdgeConfig(
            escalation_threshold=0.4,
            event_cooldown_seconds=0.1,  # Short for testing
        )
        self.filter = EdgeRiskFilter(edge_config=config)
    
    def test_no_tracks_low_risk(self):
        result = self.filter.assess([], frame_id=1)
        assert result.risk_score == 0.0
        assert result.should_escalate is False
        assert len(result.triggers) == 0
    
    def test_person_only_low_risk(self):
        tracks = [make_person()]
        result = self.filter.assess(tracks, frame_id=1)
        assert result.risk_score == 0.0
        assert result.should_escalate is False
    
    def test_weapon_detected_escalates(self):
        """Weapon alone scores 0.5, exceeds threshold 0.4."""
        tracks = [make_weapon()]
        result = self.filter.assess(tracks, frame_id=1)
        assert result.risk_score >= 0.5
        assert result.should_escalate is True
        assert any("weapon_detected" in t for t in result.triggers)
    
    def test_weapon_person_coexist_escalates(self):
        """Weapon + person in same frame → higher score."""
        tracks = [make_person(), make_weapon(bbox=(500, 500, 550, 550))]
        result = self.filter.assess(tracks, frame_id=1)
        assert result.risk_score >= 0.8  # 0.5 + 0.3
        assert result.should_escalate is True
        assert any("weapon_person_coexist" in t for t in result.triggers)
    
    def test_weapon_person_overlap_highest_risk(self):
        """Weapon overlapping person bbox → highest score."""
        person = make_person(bbox=(100, 100, 300, 400))
        weapon = make_weapon(bbox=(150, 200, 250, 300))  # Inside person
        tracks = [person, weapon]
        result = self.filter.assess(tracks, frame_id=1)
        assert result.risk_score >= 0.8
        assert result.should_escalate is True
        overlap_triggers = [t for t in result.triggers if "overlap" in t or "inside" in t]
        assert len(overlap_triggers) > 0
    
    def test_animal_no_escalation(self):
        """Animal alone should not escalate."""
        tracks = [make_animal()]
        result = self.filter.assess(tracks, frame_id=1)
        assert result.should_escalate is False
    
    def test_cooldown_prevents_double_escalation(self):
        """Same track should not escalate twice within cooldown."""
        tracks = [make_weapon()]
        
        r1 = self.filter.assess(tracks, frame_id=1)
        assert r1.should_escalate is True
        
        # Immediately again — should be cooled down
        r2 = self.filter.assess(tracks, frame_id=2)
        assert r2.should_escalate is False
    
    def test_cooldown_expires(self):
        """After cooldown expires, should escalate again."""
        tracks = [make_weapon()]
        
        r1 = self.filter.assess(tracks, frame_id=1)
        assert r1.should_escalate is True
        
        # Wait for cooldown (0.1s)
        time.sleep(0.15)
        
        r2 = self.filter.assess(tracks, frame_id=2)
        assert r2.should_escalate is True
    
    def test_track_summaries_populated(self):
        tracks = [make_person(), make_weapon()]
        result = self.filter.assess(tracks, frame_id=1)
        assert len(result.track_summaries) == 2
        assert result.track_summaries[0].is_person is True
        assert result.track_summaries[1].is_weapon is True
    
    def test_create_event(self):
        """Test event creation with frame compression."""
        tracks = [make_weapon()]
        assessment = self.filter.assess(tracks, frame_id=42)
        
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        event = self.filter.create_event(frame, assessment, camera_id="cam1")
        
        assert isinstance(event, SuspiciousEvent)
        assert event.camera_id == "cam1"
        assert event.frame_id == 42
        assert len(event.frame_jpeg) > 0
        assert event.frame_width == 640
        assert event.frame_height == 480
        assert event.edge_risk_score >= 0.5
    
    def test_stats(self):
        tracks = [make_person()]
        self.filter.assess(tracks, frame_id=1)
        self.filter.assess(tracks, frame_id=2)
        
        stats = self.filter.get_stats()
        assert stats["total_frames"] == 2
        assert stats["total_escalations"] == 0
    
    def test_score_clamped_at_1(self):
        """Score should never exceed 1.0."""
        person = make_person(bbox=(100, 100, 300, 400))
        weapon = make_weapon(bbox=(100, 100, 300, 400))  # Same bbox
        tracks = [person, weapon]
        result = self.filter.assess(tracks, frame_id=1)
        assert result.risk_score <= 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
