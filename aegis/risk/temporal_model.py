"""
AegisAI - Smart City Risk Intelligence System
Temporal Risk Model Module

This module handles risk escalation and decay over time.
Ensures gradual risk changes without sudden spikes.

Features:
- Gradual risk escalation for persistent suspicious behavior
- Smooth decay when behavior normalizes
- Per-track temporal state tracking
- Configurable escalation/decay rates

Phase 3: Risk Intelligence Layer
"""

import logging
from typing import Dict, Optional
from dataclasses import dataclass, field
from collections import defaultdict

# Configure module logger
logger = logging.getLogger(__name__)


@dataclass
class TemporalConfig:
    """
    Configuration for temporal risk adjustment.
    
    Attributes:
        escalation_rate: Risk increase per frame during suspicious behavior
        decay_rate: Risk decrease per frame during normal behavior
        min_persistence_frames: Frames of suspicious behavior before escalation
        max_temporal_adjustment: Maximum temporal adjustment value
        decay_delay_frames: Frames of normal behavior before decay starts
    """
    escalation_rate: float = 0.02
    decay_rate: float = 0.01
    min_persistence_frames: int = 30
    max_temporal_adjustment: float = 0.3
    decay_delay_frames: int = 15


@dataclass
class TemporalState:
    """
    Per-track temporal state for risk calculation.
    
    Attributes:
        track_id: Track identifier
        adjustment: Current temporal adjustment value
        suspicious_frames: Consecutive frames with suspicious behavior
        normal_frames: Consecutive frames with normal behavior
        peak_adjustment: Highest adjustment reached
        last_update_frame: Frame of last update
    """
    track_id: int
    adjustment: float = 0.0
    suspicious_frames: int = 0
    normal_frames: int = 0
    peak_adjustment: float = 0.0
    last_update_frame: int = 0
    
    def is_escalating(self, config: TemporalConfig) -> bool:
        """Check if currently in escalation phase."""
        return self.suspicious_frames >= config.min_persistence_frames
    
    def is_decaying(self, config: TemporalConfig) -> bool:
        """Check if currently in decay phase."""
        return self.normal_frames >= config.decay_delay_frames


class TemporalRiskModel:
    """
    Manages temporal risk escalation and decay.
    
    Tracks persistent suspicious behavior and adjusts risk scores
    accordingly. Ensures smooth transitions without sudden spikes.
    
    Attributes:
        config: Temporal configuration
        states: Per-track temporal states
        
    Example:
        >>> model = TemporalRiskModel()
        >>> state = model.update(track_id=1, is_suspicious=True, frame_id=100)
        >>> adjusted_score = base_score + state.adjustment
    """
    
    def __init__(self, config: Optional[TemporalConfig] = None):
        """
        Initialize the temporal risk model.
        
        Args:
            config: Temporal configuration
        """
        self._config = config or TemporalConfig()
        self._states: Dict[int, TemporalState] = {}
        
        logger.info(
            f"TemporalRiskModel initialized with "
            f"escalation_rate={self._config.escalation_rate}, "
            f"decay_rate={self._config.decay_rate}"
        )
    
    @property
    def config(self) -> TemporalConfig:
        """Get the temporal configuration."""
        return self._config
    
    @property
    def active_tracks(self) -> int:
        """Get number of tracks with temporal state."""
        return len(self._states)
    
    def update(
        self,
        track_id: int,
        is_suspicious: bool,
        frame_id: int
    ) -> TemporalState:
        """
        Update temporal state for a track.
        
        Args:
            track_id: Track identifier
            is_suspicious: Whether current behavior is suspicious
            frame_id: Current frame number
            
        Returns:
            Updated TemporalState
        """
        # Get or create state
        if track_id not in self._states:
            self._states[track_id] = TemporalState(track_id=track_id)
        
        state = self._states[track_id]
        state.last_update_frame = frame_id
        
        if is_suspicious:
            # Increment suspicious counter, reset normal counter
            state.suspicious_frames += 1
            state.normal_frames = 0
            
            # Check if should escalate
            if state.suspicious_frames >= self._config.min_persistence_frames:
                # Apply escalation
                new_adjustment = min(
                    state.adjustment + self._config.escalation_rate,
                    self._config.max_temporal_adjustment
                )
                state.adjustment = new_adjustment
                state.peak_adjustment = max(state.peak_adjustment, new_adjustment)
                
                logger.debug(
                    f"Track {track_id} escalating: adjustment={state.adjustment:.3f}"
                )
        else:
            # Increment normal counter, reset suspicious counter
            state.normal_frames += 1
            state.suspicious_frames = 0
            
            # Check if should decay
            if state.normal_frames >= self._config.decay_delay_frames:
                # Apply decay
                new_adjustment = max(
                    state.adjustment - self._config.decay_rate,
                    0.0
                )
                state.adjustment = new_adjustment
                
                if state.adjustment == 0.0 and new_adjustment < state.adjustment:
                    logger.debug(f"Track {track_id} risk fully decayed")
        
        return state
    
    def get_state(self, track_id: int) -> TemporalState:
        """
        Get temporal state for a track.
        
        Args:
            track_id: Track identifier
            
        Returns:
            TemporalState (creates new if not exists)
        """
        if track_id not in self._states:
            self._states[track_id] = TemporalState(track_id=track_id)
        return self._states[track_id]
    
    def get_adjustment(self, track_id: int) -> float:
        """
        Get current temporal adjustment for a track.
        
        Args:
            track_id: Track identifier
            
        Returns:
            Temporal adjustment value
        """
        if track_id in self._states:
            return self._states[track_id].adjustment
        return 0.0
    
    def cleanup_stale_tracks(self, current_frame: int, max_age: int = 90) -> int:
        """
        Remove tracks that haven't been updated recently.
        
        Args:
            current_frame: Current frame number
            max_age: Maximum frames since last update
            
        Returns:
            Number of tracks removed
        """
        stale_ids = []
        for track_id, state in self._states.items():
            if current_frame - state.last_update_frame > max_age:
                stale_ids.append(track_id)
        
        for track_id in stale_ids:
            del self._states[track_id]
        
        if stale_ids:
            logger.debug(f"Cleaned up {len(stale_ids)} stale temporal states")
        
        return len(stale_ids)
    
    def reset(self) -> None:
        """Reset all temporal states."""
        self._states.clear()
        logger.info("TemporalRiskModel reset")
    
    def get_statistics(self) -> dict:
        """
        Get statistics about temporal states.
        
        Returns:
            Dictionary with statistics
        """
        if not self._states:
            return {
                "active_tracks": 0,
                "escalating_tracks": 0,
                "avg_adjustment": 0.0,
                "max_adjustment": 0.0
            }
        
        adjustments = [s.adjustment for s in self._states.values()]
        escalating = sum(
            1 for s in self._states.values()
            if s.is_escalating(self._config)
        )
        
        return {
            "active_tracks": len(self._states),
            "escalating_tracks": escalating,
            "avg_adjustment": sum(adjustments) / len(adjustments),
            "max_adjustment": max(adjustments)
        }
    
    def __repr__(self) -> str:
        return (
            f"TemporalRiskModel(tracks={len(self._states)}, "
            f"escalation_rate={self._config.escalation_rate})"
        )
