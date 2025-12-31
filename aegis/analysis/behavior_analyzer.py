"""
AegisAI - Smart City Risk Intelligence System
Behavior Analyzer Module

This module detects behavioral patterns from motion and history data.
Identifies anomalies such as loitering, sudden movements, and direction reversals.

Features:
- Loitering detection (stationary for extended time)
- Sudden speed change detection
- Direction reversal detection
- Erratic motion detection
- Running detection (for persons)

Phase 2: Analysis Layer
"""

import logging
import math
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from aegis.analysis.analysis_types import (
    BehaviorFlags,
    BehaviorType,
    MotionState,
    TrackAnalysis
)
from aegis.analysis.track_history import TrackHistory, TrackHistoryManager
from aegis.analysis.motion_analyzer import MotionAnalyzer

# Configure module logger
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BehaviorAnalyzerConfig:
    """
    Configuration for behavior analysis.
    
    Attributes:
        loitering_time_threshold: Seconds stationary to trigger loitering
        speed_change_threshold: Multiplier for detecting sudden speed change
        direction_reversal_threshold: Radians change to detect reversal (135°)
        erratic_variance_threshold: Direction variance for erratic detection
        running_speed_threshold: Speed to consider as running
        min_history_for_behavior: Minimum history for behavior analysis
        assumed_fps: Frame rate for time calculations
    """
    loitering_time_threshold: float = 5.0  # seconds
    speed_change_threshold: float = 3.0  # multiplier
    direction_reversal_threshold: float = 2.356  # ~135 degrees in radians
    erratic_variance_threshold: float = 0.5  # circular variance (0-1)
    running_speed_threshold: float = 15.0  # pixels per frame
    min_history_for_behavior: int = 5
    assumed_fps: float = 30.0


class BehaviorAnalyzer:
    """
    Analyzes behavioral patterns from track motion data.
    
    Detects anomalies and unusual behaviors such as loitering,
    sudden movements, and erratic motion patterns.
    
    Attributes:
        config: Behavior analyzer configuration
        motion_analyzer: Motion analyzer for computing metrics
        
    Example:
        >>> analyzer = BehaviorAnalyzer()
        >>> behavior = analyzer.analyze_track(history, motion_state)
        >>> if behavior.is_loitering:
        ...     print(f"Track {track_id} is loitering!")
    """
    
    def __init__(
        self,
        config: Optional[BehaviorAnalyzerConfig] = None,
        motion_analyzer: Optional[MotionAnalyzer] = None
    ):
        """
        Initialize the behavior analyzer.
        
        Args:
            config: Behavior analyzer configuration
            motion_analyzer: Motion analyzer instance (created if not provided)
        """
        self._config = config or BehaviorAnalyzerConfig()
        self._motion_analyzer = motion_analyzer or MotionAnalyzer()
        
        # Track stationary start times for loitering detection
        self._stationary_start: Dict[int, float] = {}
        
        # Track previous speeds for sudden change detection
        self._previous_speeds: Dict[int, List[float]] = {}
        
        logger.info(
            f"BehaviorAnalyzer initialized with "
            f"loitering_threshold={self._config.loitering_time_threshold}s"
        )
    
    @property
    def config(self) -> BehaviorAnalyzerConfig:
        """Get the analyzer configuration."""
        return self._config
    
    def analyze_track(
        self,
        history: TrackHistory,
        motion_state: MotionState
    ) -> BehaviorFlags:
        """
        Analyze behavior for a single track.
        
        Args:
            history: Track history with position records
            motion_state: Current motion state for the track
            
        Returns:
            BehaviorFlags with detected behaviors
        """
        # Check minimum history requirement
        if history.history_length < self._config.min_history_for_behavior:
            return BehaviorFlags()
        
        # Initialize behavior flags
        is_stationary = not motion_state.is_moving
        is_loitering = False
        sudden_speed_change = False
        direction_reversal = False
        is_erratic = False
        is_running = False
        anomaly_score = 0.0
        
        # Get current timestamp
        current_time = history.last_seen_time
        track_id = history.track_id
        
        # Check loitering
        is_loitering = self._check_loitering(
            track_id, is_stationary, current_time
        )
        
        # Check sudden speed change
        sudden_speed_change = self._check_sudden_speed_change(
            track_id, motion_state.speed_smoothed
        )
        
        # Check direction reversal
        direction_reversal = self._check_direction_reversal(history)
        
        # Check erratic motion
        is_erratic = self._check_erratic_motion(history)
        
        # Check running (for persons only)
        if history.class_name == "Person":
            is_running = motion_state.speed_smoothed > self._config.running_speed_threshold
        
        # Compute anomaly score (0-1)
        anomaly_score = self._compute_anomaly_score(
            is_loitering=is_loitering,
            sudden_speed_change=sudden_speed_change,
            direction_reversal=direction_reversal,
            is_erratic=is_erratic
        )
        
        return BehaviorFlags(
            is_stationary=is_stationary,
            is_loitering=is_loitering,
            sudden_speed_change=sudden_speed_change,
            direction_reversal=direction_reversal,
            is_erratic=is_erratic,
            is_running=is_running,
            anomaly_score=anomaly_score
        )
    
    def analyze_all(
        self,
        history_manager: TrackHistoryManager,
        motion_states: Dict[int, MotionState]
    ) -> Dict[int, BehaviorFlags]:
        """
        Analyze behavior for all active tracks.
        
        Args:
            history_manager: Track history manager
            motion_states: Motion states for all tracks
            
        Returns:
            Dictionary mapping track_id to BehaviorFlags
        """
        behaviors = {}
        
        for history in history_manager.get_recently_updated():
            track_id = history.track_id
            motion_state = motion_states.get(track_id, MotionState())
            behaviors[track_id] = self.analyze_track(history, motion_state)
        
        # Count anomalies
        anomaly_count = sum(1 for b in behaviors.values() if b.has_anomaly)
        if anomaly_count > 0:
            logger.debug(f"Detected anomalies in {anomaly_count} tracks")
        
        return behaviors
    
    def _check_loitering(
        self,
        track_id: int,
        is_stationary: bool,
        current_time: float
    ) -> bool:
        """
        Check if a track is loitering (stationary for extended time).
        
        Args:
            track_id: Track identifier
            is_stationary: Whether track is currently stationary
            current_time: Current timestamp
            
        Returns:
            True if loitering is detected
        """
        if is_stationary:
            if track_id not in self._stationary_start:
                self._stationary_start[track_id] = current_time
            else:
                stationary_duration = current_time - self._stationary_start[track_id]
                if stationary_duration >= self._config.loitering_time_threshold:
                    return True
        else:
            # Reset stationary timer when moving
            if track_id in self._stationary_start:
                del self._stationary_start[track_id]
        
        return False
    
    def _check_sudden_speed_change(
        self,
        track_id: int,
        current_speed: float
    ) -> bool:
        """
        Check for sudden change in speed.
        
        Args:
            track_id: Track identifier
            current_speed: Current smoothed speed
            
        Returns:
            True if sudden speed change detected
        """
        # Initialize or get previous speeds
        if track_id not in self._previous_speeds:
            self._previous_speeds[track_id] = []
        
        speeds = self._previous_speeds[track_id]
        
        # Keep last 5 speeds
        speeds.append(current_speed)
        if len(speeds) > 5:
            speeds.pop(0)
        
        # Need at least 3 speeds to detect change
        if len(speeds) < 3:
            return False
        
        # Compute average of previous speeds
        avg_previous = sum(speeds[:-1]) / (len(speeds) - 1)
        
        # Avoid division by zero
        if avg_previous < 0.1:
            # If was nearly stationary and now moving fast
            return current_speed > self._config.running_speed_threshold
        
        # Check for sudden change
        ratio = current_speed / avg_previous
        return (
            ratio > self._config.speed_change_threshold or
            ratio < 1 / self._config.speed_change_threshold
        )
    
    def _check_direction_reversal(self, history: TrackHistory) -> bool:
        """
        Check for direction reversal (>135° change).
        
        Args:
            history: Track history
            
        Returns:
            True if direction reversal detected
        """
        direction_change = self._motion_analyzer.compute_direction_change(
            history, window=5
        )
        return direction_change > self._config.direction_reversal_threshold
    
    def _check_erratic_motion(self, history: TrackHistory) -> bool:
        """
        Check for erratic (high variance) motion.
        
        Args:
            history: Track history
            
        Returns:
            True if erratic motion detected
        """
        variance = self._motion_analyzer.compute_direction_variance(
            history, window=10
        )
        return variance > self._config.erratic_variance_threshold
    
    def _compute_anomaly_score(
        self,
        is_loitering: bool,
        sudden_speed_change: bool,
        direction_reversal: bool,
        is_erratic: bool
    ) -> float:
        """
        Compute composite anomaly score.
        
        Args:
            is_loitering: Loitering flag
            sudden_speed_change: Sudden speed change flag
            direction_reversal: Direction reversal flag
            is_erratic: Erratic motion flag
            
        Returns:
            Anomaly score between 0 and 1
        """
        # Weighted sum of anomaly flags
        weights = {
            'loitering': 0.3,
            'sudden_speed': 0.25,
            'reversal': 0.2,
            'erratic': 0.25
        }
        
        score = 0.0
        if is_loitering:
            score += weights['loitering']
        if sudden_speed_change:
            score += weights['sudden_speed']
        if direction_reversal:
            score += weights['reversal']
        if is_erratic:
            score += weights['erratic']
        
        return min(score, 1.0)
    
    def cleanup_track(self, track_id: int) -> None:
        """
        Clean up state for a removed track.
        
        Args:
            track_id: Track identifier to clean up
        """
        if track_id in self._stationary_start:
            del self._stationary_start[track_id]
        if track_id in self._previous_speeds:
            del self._previous_speeds[track_id]
    
    def reset(self) -> None:
        """Reset all analyzer state."""
        self._stationary_start.clear()
        self._previous_speeds.clear()
        logger.info("BehaviorAnalyzer reset")
    
    def __repr__(self) -> str:
        return (
            f"BehaviorAnalyzer(loitering_threshold="
            f"{self._config.loitering_time_threshold}s)"
        )
