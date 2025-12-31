"""
AegisAI - Semantic Trigger
Event-Driven DINO Invocation Logic

This module determines WHEN to invoke Grounding DINO based on events.
CRITICAL: No per-frame inference - DINO only runs on specific triggers.

Trigger Conditions:
1. User submits a text query
2. Tracked object changes behavior (loitering, sudden stop, zone violation)
3. Risk score exceeds predefined threshold

Features:
- Event-driven design
- Configurable thresholds
- Track-specific triggering
"""

import logging
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional, Dict, Any

import numpy as np

# Configure module logger
logger = logging.getLogger(__name__)


class TriggerType(Enum):
    """Types of semantic trigger events."""
    USER_QUERY = auto()          # User submitted a text query
    RISK_THRESHOLD = auto()      # Risk score exceeded threshold
    BEHAVIOR_CHANGE = auto()     # Track behavior changed (loitering, etc.)
    ZONE_VIOLATION = auto()      # Track entered restricted zone


@dataclass
class TriggerEvent:
    """
    Semantic trigger event container.
    
    Attributes:
        track_id: ID of the track that triggered
        trigger_type: Type of trigger
        prompt: The semantic prompt to use
        cropped_frame: Cropped image region for the track
        priority: Event priority (higher = more urgent)
        metadata: Additional context data
    """
    track_id: int
    trigger_type: TriggerType
    prompt: str
    cropped_frame: np.ndarray
    priority: int = 0
    metadata: Optional[Dict[str, Any]] = None


class SemanticTrigger:
    """
    Event-driven trigger for semantic inference.
    
    Determines when to invoke Grounding DINO based on behavioral
    signals, risk scores, and user queries. Ensures DINO is only
    called when necessary to preserve real-time performance.
    
    Attributes:
        config: Semantic configuration
        
    Example:
        >>> trigger = SemanticTrigger(config.semantic)
        >>> events = trigger.check_triggers(tracks, risk_scores, user_query)
        >>> for event in events:
        ...     executor.submit(event.track_id, event.cropped_frame, event.prompt)
    """
    
    def __init__(self, config):
        """
        Initialize the semantic trigger.
        
        Args:
            config: SemanticConfig instance
        """
        self._config = config
        self._triggered_tracks: Dict[int, float] = {}  # track_id -> last_trigger_time
        self._cooldown_seconds = 5.0  # Minimum time between triggers per track
        
        logger.info(
            f"SemanticTrigger initialized with "
            f"risk_threshold={config.risk_threshold_trigger}"
        )
    
    def check_triggers(
        self,
        tracks: List[Any],  # List[TrackAnalysis]
        risk_scores: Optional[Any] = None,  # FrameRiskSummary
        user_query: Optional[str] = None,
        frame: Optional[np.ndarray] = None
    ) -> List[TriggerEvent]:
        """
        Check for trigger conditions and return events.
        
        Args:
            tracks: List of TrackAnalysis objects
            risk_scores: Optional FrameRiskSummary with track risks
            user_query: Optional user-submitted semantic query
            frame: Full video frame (for cropping)
            
        Returns:
            List of TriggerEvent objects for tracks needing DINO
        """
        import time
        current_time = time.time()
        events: List[TriggerEvent] = []
        
        if frame is None:
            logger.warning("No frame provided, cannot generate trigger events")
            return events
        
        # Build risk map for quick lookup
        risk_map: Dict[int, float] = {}
        if risk_scores and hasattr(risk_scores, 'track_risks'):
            for risk in risk_scores.track_risks:
                risk_map[risk.track_id] = risk.score
        
        for track in tracks:
            track_id = track.track_id if hasattr(track, 'track_id') else 0
            
            # Check cooldown
            if self._is_on_cooldown(track_id, current_time):
                continue
            
            # Get track bbox for cropping
            bbox = track.current_bbox if hasattr(track, 'current_bbox') else None
            if bbox is None:
                continue
            
            # Determine prompts and triggers
            triggered = False
            prompt = ""
            trigger_type = None
            priority = 0
            
            # ═══════════════════════════════════════════════════════════
            # TRIGGER 1: User Query (highest priority)
            # ═══════════════════════════════════════════════════════════
            if user_query:
                triggered = True
                prompt = user_query
                trigger_type = TriggerType.USER_QUERY
                priority = 100
            
            # ═══════════════════════════════════════════════════════════
            # TRIGGER 2: Risk Threshold Exceeded
            # ═══════════════════════════════════════════════════════════
            elif risk_map.get(track_id, 0) >= self._config.risk_threshold_trigger:
                triggered = True
                prompt = self._generate_risk_prompt(track)
                trigger_type = TriggerType.RISK_THRESHOLD
                priority = 80
            
            # ═══════════════════════════════════════════════════════════
            # TRIGGER 3: Behavior Change
            # ═══════════════════════════════════════════════════════════
            elif self._has_behavior_trigger(track):
                triggered = True
                prompt = self._generate_behavior_prompt(track)
                trigger_type = TriggerType.BEHAVIOR_CHANGE
                priority = 60
            
            # Create event if triggered
            if triggered and prompt:
                cropped = self._crop_track_region(frame, bbox)
                
                event = TriggerEvent(
                    track_id=track_id,
                    trigger_type=trigger_type,
                    prompt=prompt,
                    cropped_frame=cropped,
                    priority=priority,
                    metadata={
                        "risk_score": risk_map.get(track_id, 0),
                        "class_name": getattr(track, 'class_name', 'unknown')
                    }
                )
                events.append(event)
                self._triggered_tracks[track_id] = current_time
                
                logger.debug(
                    f"Trigger: {trigger_type.name} for track {track_id}, "
                    f"prompt='{prompt[:50]}...'"
                )
        
        # Sort by priority
        events.sort(key=lambda e: e.priority, reverse=True)
        
        if events:
            logger.info(f"Generated {len(events)} semantic trigger events")
        
        return events
    
    def _is_on_cooldown(self, track_id: int, current_time: float) -> bool:
        """Check if track is on trigger cooldown."""
        last_trigger = self._triggered_tracks.get(track_id, 0)
        return current_time - last_trigger < self._cooldown_seconds
    
    def _has_behavior_trigger(self, track) -> bool:
        """Check if track has behavior-based trigger conditions."""
        behavior = getattr(track, 'behavior', None)
        if behavior is None:
            return False
        
        # Trigger on concerning behaviors
        return any([
            getattr(behavior, 'is_loitering', False),
            getattr(behavior, 'sudden_speed_change', False),
            getattr(behavior, 'direction_reversal', False),
            getattr(behavior, 'is_erratic', False),
        ])
    
    def _generate_risk_prompt(self, track) -> str:
        """Generate a contextual prompt for high-risk tracks."""
        class_name = getattr(track, 'class_name', 'person').lower()
        return f"{class_name} suspicious behavior dangerous item weapon bag"
    
    def _generate_behavior_prompt(self, track) -> str:
        """Generate a prompt based on detected behaviors."""
        class_name = getattr(track, 'class_name', 'person').lower()
        behavior = getattr(track, 'behavior', None)
        
        prompts = [class_name]
        
        if behavior:
            if getattr(behavior, 'is_loitering', False):
                prompts.append("waiting standing idle loitering")
            if getattr(behavior, 'is_running', False):
                prompts.append("running fleeing escaping")
            if getattr(behavior, 'is_erratic', False):
                prompts.append("erratic suspicious confused")
        
        return " ".join(prompts)
    
    def _crop_track_region(
        self,
        frame: np.ndarray,
        bbox: tuple,
        padding: float = 0.1
    ) -> np.ndarray:
        """
        Crop the frame region around a track with padding.
        
        Args:
            frame: Full video frame
            bbox: (x1, y1, x2, y2) bounding box
            padding: Relative padding around bbox
            
        Returns:
            Cropped image region
        """
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = bbox
        
        # Add padding
        pad_w = int((x2 - x1) * padding)
        pad_h = int((y2 - y1) * padding)
        
        x1 = max(0, x1 - pad_w)
        y1 = max(0, y1 - pad_h)
        x2 = min(w, x2 + pad_w)
        y2 = min(h, y2 + pad_h)
        
        return frame[y1:y2, x1:x2].copy()
    
    def set_cooldown(self, seconds: float) -> None:
        """Set the per-track trigger cooldown."""
        self._cooldown_seconds = max(0.0, seconds)
    
    def clear_cooldowns(self) -> None:
        """Clear all track cooldowns."""
        self._triggered_tracks.clear()
    
    def __repr__(self) -> str:
        return (
            f"SemanticTrigger(threshold={self._config.risk_threshold_trigger}, "
            f"active_tracks={len(self._triggered_tracks)})"
        )
