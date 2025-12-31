"""
AegisAI - Smart City Risk Intelligence System
Motion Analyzer Module

This module computes motion metrics from track history data.
Analyzes speed, velocity, direction, and acceleration for each track.

Features:
- Speed estimation (pixels per frame)
- Velocity vector computation
- Direction calculation (radians and degrees)
- Acceleration detection
- Smoothed metrics using moving average

Phase 2: Analysis Layer
"""

import logging
import math
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from aegis.analysis.analysis_types import MotionState, PositionRecord
from aegis.analysis.track_history import TrackHistory, TrackHistoryManager

# Configure module logger
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MotionAnalyzerConfig:
    """
    Configuration for motion analysis.
    
    Attributes:
        smoothing_window: Frames for moving average smoothing
        stationary_threshold: Speed below this is considered stationary
        min_history_for_analysis: Minimum positions needed for analysis
        running_threshold: Speed above this is considered running (for persons)
    """
    smoothing_window: int = 5
    stationary_threshold: float = 2.0  # pixels per frame
    min_history_for_analysis: int = 3
    running_threshold: float = 15.0  # pixels per frame


class MotionAnalyzer:
    """
    Analyzes motion patterns from track history.
    
    Computes speed, velocity, direction, and acceleration
    for tracked objects based on their position history.
    
    Attributes:
        config: Motion analyzer configuration
        
    Example:
        >>> analyzer = MotionAnalyzer()
        >>> motion = analyzer.analyze_track(history)
        >>> print(f"Speed: {motion.speed:.2f} px/frame")
        >>> print(f"Direction: {motion.direction_degrees:.1f}°")
    """
    
    def __init__(self, config: Optional[MotionAnalyzerConfig] = None):
        """
        Initialize the motion analyzer.
        
        Args:
            config: Motion analyzer configuration
        """
        self._config = config or MotionAnalyzerConfig()
        logger.info(
            f"MotionAnalyzer initialized with stationary_threshold="
            f"{self._config.stationary_threshold}"
        )
    
    @property
    def config(self) -> MotionAnalyzerConfig:
        """Get the analyzer configuration."""
        return self._config
    
    def analyze_track(self, history: TrackHistory) -> MotionState:
        """
        Compute motion state for a single track.
        
        Args:
            history: Track history with position records
            
        Returns:
            MotionState with computed metrics
        """
        # Check minimum history requirement
        if history.history_length < self._config.min_history_for_analysis:
            return MotionState(
                speed=0.0,
                speed_smoothed=0.0,
                velocity=(0.0, 0.0),
                direction=0.0,
                acceleration=0.0,
                is_moving=False,
                distance_traveled=history.total_distance
            )
        
        # Get current and previous positions
        current = history.current_position
        previous = history.previous_position
        
        if current is None or previous is None:
            return MotionState(distance_traveled=history.total_distance)
        
        # Compute instantaneous velocity
        dx = current.x - previous.x
        dy = current.y - previous.y
        
        # Compute instantaneous speed
        speed = math.sqrt(dx * dx + dy * dy)
        
        # Compute direction (radians, 0 = right, π/2 = up)
        direction = math.atan2(-dy, dx)  # Negative dy because y increases downward
        
        # Compute smoothed speed using moving average
        speed_smoothed = self._compute_smoothed_speed(history)
        
        # Compute acceleration
        acceleration = self._compute_acceleration(history)
        
        # Determine if moving
        is_moving = speed_smoothed > self._config.stationary_threshold
        
        return MotionState(
            speed=speed,
            speed_smoothed=speed_smoothed,
            velocity=(dx, dy),
            direction=direction,
            acceleration=acceleration,
            is_moving=is_moving,
            distance_traveled=history.total_distance
        )
    
    def analyze_all(
        self,
        history_manager: TrackHistoryManager
    ) -> Dict[int, MotionState]:
        """
        Compute motion states for all active tracks.
        
        Args:
            history_manager: Track history manager with all histories
            
        Returns:
            Dictionary mapping track_id to MotionState
        """
        motion_states = {}
        
        for history in history_manager.get_recently_updated():
            motion_states[history.track_id] = self.analyze_track(history)
        
        logger.debug(f"Analyzed motion for {len(motion_states)} tracks")
        return motion_states
    
    def _compute_smoothed_speed(self, history: TrackHistory) -> float:
        """
        Compute smoothed speed using moving average.
        
        Args:
            history: Track history
            
        Returns:
            Smoothed speed value
        """
        positions = history.get_recent_positions(self._config.smoothing_window + 1)
        
        if len(positions) < 2:
            return 0.0
        
        total_speed = 0.0
        count = 0
        
        for i in range(1, len(positions)):
            prev = positions[i - 1]
            curr = positions[i]
            dx = curr.x - prev.x
            dy = curr.y - prev.y
            speed = math.sqrt(dx * dx + dy * dy)
            total_speed += speed
            count += 1
        
        return total_speed / count if count > 0 else 0.0
    
    def _compute_acceleration(self, history: TrackHistory) -> float:
        """
        Compute acceleration (change in speed).
        
        Args:
            history: Track history
            
        Returns:
            Acceleration value (positive = speeding up)
        """
        positions = history.get_recent_positions(3)
        
        if len(positions) < 3:
            return 0.0
        
        # Compute speed between last two pairs of positions
        prev2, prev1, curr = positions[-3], positions[-2], positions[-1]
        
        speed1 = math.sqrt(
            (prev1.x - prev2.x) ** 2 + (prev1.y - prev2.y) ** 2
        )
        speed2 = math.sqrt(
            (curr.x - prev1.x) ** 2 + (curr.y - prev1.y) ** 2
        )
        
        return speed2 - speed1
    
    def compute_direction_change(
        self,
        history: TrackHistory,
        window: int = 5
    ) -> float:
        """
        Compute the change in direction over a window.
        
        Args:
            history: Track history
            window: Number of frames to consider
            
        Returns:
            Direction change in radians (absolute value)
        """
        positions = history.get_recent_positions(window + 1)
        
        if len(positions) < 3:
            return 0.0
        
        # Compute initial direction
        dx1 = positions[1].x - positions[0].x
        dy1 = positions[1].y - positions[0].y
        dir1 = math.atan2(-dy1, dx1)
        
        # Compute final direction
        dx2 = positions[-1].x - positions[-2].x
        dy2 = positions[-1].y - positions[-2].y
        dir2 = math.atan2(-dy2, dx2)
        
        # Compute angular difference (handle wraparound)
        diff = abs(dir2 - dir1)
        if diff > math.pi:
            diff = 2 * math.pi - diff
        
        return diff
    
    def compute_direction_variance(
        self,
        history: TrackHistory,
        window: int = 10
    ) -> float:
        """
        Compute variance in direction over a window.
        
        High variance indicates erratic movement.
        
        Args:
            history: Track history
            window: Number of frames to consider
            
        Returns:
            Direction variance in radians squared
        """
        positions = history.get_recent_positions(window + 1)
        
        if len(positions) < 3:
            return 0.0
        
        directions = []
        for i in range(1, len(positions)):
            dx = positions[i].x - positions[i - 1].x
            dy = positions[i].y - positions[i - 1].y
            if dx != 0 or dy != 0:  # Skip zero movement
                directions.append(math.atan2(-dy, dx))
        
        if len(directions) < 2:
            return 0.0
        
        # Compute circular variance
        sin_sum = sum(math.sin(d) for d in directions)
        cos_sum = sum(math.cos(d) for d in directions)
        n = len(directions)
        
        # R is the mean resultant length (0 to 1)
        r = math.sqrt(sin_sum ** 2 + cos_sum ** 2) / n
        
        # Circular variance = 1 - R (0 = no variance, 1 = max variance)
        return 1 - r
    
    def __repr__(self) -> str:
        return (
            f"MotionAnalyzer(stationary_threshold="
            f"{self._config.stationary_threshold})"
        )
