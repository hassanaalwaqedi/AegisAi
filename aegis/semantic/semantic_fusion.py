"""
AegisAI - Semantic Fusion
Combines YOLO Detection + Tracking + DINO Semantic Matching

This module fuses multiple perception layers into unified
object intelligence with both visual and semantic understanding.

Output Structure:
{
    track_id,
    base_class,
    semantic_label,
    risk_score,
    timestamp
}
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any

from aegis.semantic.dino_engine import SemanticDetection

# Configure module logger
logger = logging.getLogger(__name__)


@dataclass
class UnifiedObjectIntelligence:
    """
    Combined perception + semantic understanding.
    
    Fuses YOLO class detection, DeepSORT tracking, Grounding DINO
    semantic matching, and risk scoring into a single intelligence object.
    
    Attributes:
        track_id: Unique tracking identifier
        base_class: YOLO detected class (e.g., "Person")
        confidence: YOLO detection confidence
        semantic_label: DINO semantic match (e.g., "person with bag")
        semantic_confidence: DINO match confidence
        matched_phrase: The specific phrase matched by DINO
        risk_score: Current risk score [0.0, 1.0]
        timestamp: Frame timestamp in seconds
        bbox: Bounding box (x1, y1, x2, y2)
        behaviors: Active behavior flags
    """
    track_id: int
    base_class: str
    confidence: float
    semantic_label: Optional[str]
    semantic_confidence: Optional[float]
    matched_phrase: Optional[str]
    risk_score: float
    timestamp: float
    bbox: Tuple[int, int, int, int]
    behaviors: List[str] = field(default_factory=list)
    
    def has_semantic_match(self) -> bool:
        """Check if semantic matching was performed."""
        return self.semantic_label is not None
    
    def is_high_risk(self, threshold: float = 0.6) -> bool:
        """Check if track is high risk."""
        return self.risk_score >= threshold
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "track_id": self.track_id,
            "base_class": self.base_class,
            "confidence": round(self.confidence, 3),
            "semantic_label": self.semantic_label,
            "semantic_confidence": round(self.semantic_confidence, 3) if self.semantic_confidence else None,
            "matched_phrase": self.matched_phrase,
            "risk_score": round(self.risk_score, 3),
            "timestamp": round(self.timestamp, 3),
            "bbox": self.bbox,
            "behaviors": self.behaviors,
            "has_semantic": self.has_semantic_match(),
            "is_high_risk": self.is_high_risk()
        }


class SemanticFusion:
    """
    Combines YOLO detection + tracking + DINO semantic matching.
    
    Creates unified intelligence objects by merging:
    - Base class from YOLO detection
    - Track ID from DeepSORT
    - Semantic labels from Grounding DINO
    - Risk scores from Risk Engine
    
    Example:
        >>> fusion = SemanticFusion()
        >>> intel = fusion.fuse(
        ...     tracks=tracks,
        ...     track_analyses=analyses,
        ...     semantic_results=dino_results,
        ...     risk_summary=risks,
        ...     timestamp=1.5
        ... )
        >>> for obj in intel:
        ...     print(f"Track {obj.track_id}: {obj.base_class} -> {obj.semantic_label}")
    """
    
    def __init__(self):
        """Initialize the semantic fusion module."""
        self._last_semantic_results: Dict[int, List[SemanticDetection]] = {}
        logger.info("SemanticFusion initialized")
    
    def fuse(
        self,
        tracks: List[Any],  # List[Track]
        track_analyses: Optional[List[Any]] = None,  # List[TrackAnalysis]
        semantic_results: Optional[Dict[int, List[SemanticDetection]]] = None,
        risk_summary: Optional[Any] = None,  # FrameRiskSummary
        timestamp: float = 0.0
    ) -> List[UnifiedObjectIntelligence]:
        """
        Fuse all perception layers into unified intelligence.
        
        Args:
            tracks: List of Track objects from DeepSORT
            track_analyses: Optional list of TrackAnalysis from behavior analyzer
            semantic_results: Optional dict mapping track_id to DINO detections
            risk_summary: Optional FrameRiskSummary with risk scores
            timestamp: Current frame timestamp
            
        Returns:
            List of UnifiedObjectIntelligence objects
        """
        # Update cached semantic results
        if semantic_results:
            self._last_semantic_results.update(semantic_results)
        
        # Build lookup maps
        analysis_map: Dict[int, Any] = {}
        if track_analyses:
            for ta in track_analyses:
                analysis_map[ta.track_id] = ta
        
        risk_map: Dict[int, float] = {}
        if risk_summary and hasattr(risk_summary, 'track_risks'):
            for risk in risk_summary.track_risks:
                risk_map[risk.track_id] = risk.score
        
        # Fuse each track
        unified: List[UnifiedObjectIntelligence] = []
        
        for track in tracks:
            track_id = track.track_id
            
            # Base detection info
            base_class = getattr(track, 'class_name', 'Unknown')
            confidence = getattr(track, 'confidence', 0.0)
            bbox = getattr(track, 'bbox', (0, 0, 0, 0))
            
            # Semantic info
            semantic_label = None
            semantic_confidence = None
            matched_phrase = None
            
            semantic_dets = self._last_semantic_results.get(track_id, [])
            if semantic_dets:
                # Use highest confidence semantic match
                best_det = max(semantic_dets, key=lambda d: d.confidence)
                semantic_label = best_det.phrase
                semantic_confidence = best_det.confidence
                matched_phrase = best_det.matched_text
            
            # Risk score
            risk_score = risk_map.get(track_id, 0.0)
            
            # Behaviors
            behaviors: List[str] = []
            analysis = analysis_map.get(track_id)
            if analysis and hasattr(analysis, 'behavior'):
                behavior = analysis.behavior
                if getattr(behavior, 'is_loitering', False):
                    behaviors.append("LOITERING")
                if getattr(behavior, 'is_running', False):
                    behaviors.append("RUNNING")
                if getattr(behavior, 'sudden_speed_change', False):
                    behaviors.append("SPEED_CHANGE")
                if getattr(behavior, 'direction_reversal', False):
                    behaviors.append("DIRECTION_REVERSAL")
                if getattr(behavior, 'is_erratic', False):
                    behaviors.append("ERRATIC")
            
            # Create unified object
            obj = UnifiedObjectIntelligence(
                track_id=track_id,
                base_class=base_class,
                confidence=confidence,
                semantic_label=semantic_label,
                semantic_confidence=semantic_confidence,
                matched_phrase=matched_phrase,
                risk_score=risk_score,
                timestamp=timestamp,
                bbox=bbox,
                behaviors=behaviors
            )
            unified.append(obj)
        
        logger.debug(
            f"Fused {len(unified)} objects, "
            f"{sum(1 for u in unified if u.has_semantic_match())} with semantic"
        )
        
        return unified
    
    def get_high_risk_objects(
        self,
        unified: List[UnifiedObjectIntelligence],
        threshold: float = 0.6
    ) -> List[UnifiedObjectIntelligence]:
        """Get objects above risk threshold."""
        return [u for u in unified if u.risk_score >= threshold]
    
    def get_semantic_matches(
        self,
        unified: List[UnifiedObjectIntelligence]
    ) -> List[UnifiedObjectIntelligence]:
        """Get objects with semantic matches."""
        return [u for u in unified if u.has_semantic_match()]
    
    def clear_semantic_cache(self) -> None:
        """Clear cached semantic results."""
        self._last_semantic_results.clear()
    
    def __repr__(self) -> str:
        return f"SemanticFusion(cached_tracks={len(self._last_semantic_results)})"
