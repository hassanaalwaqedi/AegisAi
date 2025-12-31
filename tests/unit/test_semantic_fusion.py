"""
AegisAI - Semantic Fusion Unit Tests

Tests for combining YOLO + tracking + DINO outputs.
"""

import pytest
from unittest.mock import MagicMock

from aegis.semantic.semantic_fusion import (
    SemanticFusion,
    UnifiedObjectIntelligence
)
from aegis.semantic.dino_engine import SemanticDetection


class TestSemanticFusion:
    """Tests for SemanticFusion class."""
    
    @pytest.fixture
    def fusion(self):
        """Create fusion instance."""
        return SemanticFusion()
    
    @pytest.fixture
    def sample_track(self):
        """Create sample track."""
        track = MagicMock()
        track.track_id = 1
        track.class_name = "Person"
        track.confidence = 0.92
        track.bbox = (100, 100, 200, 300)
        return track
    
    @pytest.fixture
    def sample_analysis(self):
        """Create sample track analysis."""
        analysis = MagicMock()
        analysis.track_id = 1
        analysis.behavior = MagicMock()
        analysis.behavior.is_loitering = True
        analysis.behavior.is_running = False
        analysis.behavior.sudden_speed_change = False
        analysis.behavior.direction_reversal = False
        analysis.behavior.is_erratic = False
        return analysis
    
    @pytest.fixture
    def sample_risk(self):
        """Create sample risk summary."""
        risk = MagicMock()
        risk.track_id = 1
        risk.score = 0.65
        
        summary = MagicMock()
        summary.track_risks = [risk]
        return summary
    
    def test_fusion_without_semantic(
        self, fusion, sample_track, sample_analysis, sample_risk
    ):
        """Fusion should work without semantic results."""
        result = fusion.fuse(
            tracks=[sample_track],
            track_analyses=[sample_analysis],
            semantic_results=None,
            risk_summary=sample_risk,
            timestamp=1.0
        )
        
        assert len(result) == 1
        obj = result[0]
        
        assert obj.track_id == 1
        assert obj.base_class == "Person"
        assert obj.confidence == 0.92
        assert obj.semantic_label is None
        assert obj.risk_score == 0.65
        assert "LOITERING" in obj.behaviors
    
    def test_fusion_with_semantic(
        self, fusion, sample_track, sample_analysis, sample_risk
    ):
        """Fusion should include semantic results when available."""
        semantic_results = {
            1: [
                SemanticDetection(
                    bbox=(100, 100, 200, 300),
                    confidence=0.87,
                    phrase="person with bag",
                    matched_text="person carrying bag"
                )
            ]
        }
        
        result = fusion.fuse(
            tracks=[sample_track],
            track_analyses=[sample_analysis],
            semantic_results=semantic_results,
            risk_summary=sample_risk,
            timestamp=1.0
        )
        
        assert len(result) == 1
        obj = result[0]
        
        assert obj.semantic_label == "person with bag"
        assert obj.semantic_confidence == 0.87
        assert obj.matched_phrase == "person carrying bag"
    
    def test_multiple_semantic_uses_highest_confidence(
        self, fusion, sample_track, sample_analysis, sample_risk
    ):
        """Should use semantic detection with highest confidence."""
        semantic_results = {
            1: [
                SemanticDetection(
                    bbox=(100, 100, 200, 300),
                    confidence=0.6,
                    phrase="person",
                    matched_text="test"
                ),
                SemanticDetection(
                    bbox=(100, 100, 200, 300),
                    confidence=0.9,
                    phrase="person with backpack",
                    matched_text="test"
                ),
            ]
        }
        
        result = fusion.fuse(
            tracks=[sample_track],
            track_analyses=[sample_analysis],
            semantic_results=semantic_results,
            risk_summary=sample_risk,
            timestamp=1.0
        )
        
        assert result[0].semantic_label == "person with backpack"
        assert result[0].semantic_confidence == 0.9
    
    def test_get_high_risk_objects(self, fusion):
        """Should filter high risk objects."""
        objects = [
            UnifiedObjectIntelligence(
                track_id=1, base_class="Person", confidence=0.9,
                semantic_label=None, semantic_confidence=None,
                matched_phrase=None, risk_score=0.3,
                timestamp=1.0, bbox=(0, 0, 0, 0)
            ),
            UnifiedObjectIntelligence(
                track_id=2, base_class="Person", confidence=0.9,
                semantic_label=None, semantic_confidence=None,
                matched_phrase=None, risk_score=0.8,
                timestamp=1.0, bbox=(0, 0, 0, 0)
            ),
        ]
        
        high_risk = fusion.get_high_risk_objects(objects, threshold=0.6)
        
        assert len(high_risk) == 1
        assert high_risk[0].track_id == 2
    
    def test_get_semantic_matches(self, fusion):
        """Should filter objects with semantic matches."""
        objects = [
            UnifiedObjectIntelligence(
                track_id=1, base_class="Person", confidence=0.9,
                semantic_label=None, semantic_confidence=None,
                matched_phrase=None, risk_score=0.5,
                timestamp=1.0, bbox=(0, 0, 0, 0)
            ),
            UnifiedObjectIntelligence(
                track_id=2, base_class="Person", confidence=0.9,
                semantic_label="person with bag", semantic_confidence=0.8,
                matched_phrase="test", risk_score=0.5,
                timestamp=1.0, bbox=(0, 0, 0, 0)
            ),
        ]
        
        matches = fusion.get_semantic_matches(objects)
        
        assert len(matches) == 1
        assert matches[0].track_id == 2


class TestUnifiedObjectIntelligence:
    """Tests for UnifiedObjectIntelligence dataclass."""
    
    def test_has_semantic_match(self):
        """Should correctly identify semantic matches."""
        obj_with = UnifiedObjectIntelligence(
            track_id=1, base_class="Person", confidence=0.9,
            semantic_label="test", semantic_confidence=0.8,
            matched_phrase="test", risk_score=0.5,
            timestamp=1.0, bbox=(0, 0, 0, 0)
        )
        
        obj_without = UnifiedObjectIntelligence(
            track_id=2, base_class="Person", confidence=0.9,
            semantic_label=None, semantic_confidence=None,
            matched_phrase=None, risk_score=0.5,
            timestamp=1.0, bbox=(0, 0, 0, 0)
        )
        
        assert obj_with.has_semantic_match() is True
        assert obj_without.has_semantic_match() is False
    
    def test_is_high_risk(self):
        """Should correctly identify high risk."""
        obj_high = UnifiedObjectIntelligence(
            track_id=1, base_class="Person", confidence=0.9,
            semantic_label=None, semantic_confidence=None,
            matched_phrase=None, risk_score=0.8,
            timestamp=1.0, bbox=(0, 0, 0, 0)
        )
        
        obj_low = UnifiedObjectIntelligence(
            track_id=2, base_class="Person", confidence=0.9,
            semantic_label=None, semantic_confidence=None,
            matched_phrase=None, risk_score=0.3,
            timestamp=1.0, bbox=(0, 0, 0, 0)
        )
        
        assert obj_high.is_high_risk(threshold=0.6) is True
        assert obj_low.is_high_risk(threshold=0.6) is False
    
    def test_to_dict(self):
        """Should correctly serialize to dict."""
        obj = UnifiedObjectIntelligence(
            track_id=1, base_class="Person", confidence=0.925,
            semantic_label="person with bag", semantic_confidence=0.871,
            matched_phrase="test prompt", risk_score=0.654,
            timestamp=1.234, bbox=(100, 100, 200, 300),
            behaviors=["LOITERING"]
        )
        
        d = obj.to_dict()
        
        assert d["track_id"] == 1
        assert d["base_class"] == "Person"
        assert d["confidence"] == 0.925
        assert d["semantic_label"] == "person with bag"
        assert d["risk_score"] == 0.654
        assert d["has_semantic"] is True
        assert d["is_high_risk"] is True
