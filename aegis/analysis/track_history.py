"""
AegisAI - Smart City Risk Intelligence System
Track History Manager Module

This module maintains per-track time series data for motion analysis.
Provides sliding window storage and efficient history access.

Features:
- Per-track position history with timestamps
- Configurable sliding window size
- Automatic cleanup of stale tracks
- Thread-safe design for future multi-threading

Phase 2: Analysis Layer
"""

import logging
from typing import Dict, List, Optional, Tuple
from collections import deque
from dataclasses import dataclass, field

from aegis.analysis.analysis_types import PositionRecord
from aegis.tracking.deepsort_tracker import Track

# Configure module logger
logger = logging.getLogger(__name__)


@dataclass
class TrackHistory:
    """
    Time series history for a single track.
    
    Attributes:
        track_id: Unique identifier for this track
        class_id: Object class identifier
        class_name: Human-readable class name
        positions: Deque of position records (sliding window)
        first_seen_frame: Frame when track was first observed
        first_seen_time: Timestamp when track was first observed
        last_seen_frame: Frame when track was last observed
        last_seen_time: Timestamp when track was last observed
        total_distance: Cumulative distance traveled
    """
    track_id: int
    class_id: int
    class_name: str
    positions: deque = field(default_factory=lambda: deque(maxlen=60))
    first_seen_frame: int = 0
    first_seen_time: float = 0.0
    last_seen_frame: int = 0
    last_seen_time: float = 0.0
    total_distance: float = 0.0
    
    @property
    def duration(self) -> float:
        """Get total time tracked in seconds."""
        return self.last_seen_time - self.first_seen_time
    
    @property
    def frame_count(self) -> int:
        """Get total frames tracked."""
        return self.last_seen_frame - self.first_seen_frame + 1
    
    @property
    def history_length(self) -> int:
        """Get number of positions in history."""
        return len(self.positions)
    
    def get_recent_positions(self, n: int = 5) -> List[PositionRecord]:
        """Get the N most recent positions."""
        if n >= len(self.positions):
            return list(self.positions)
        return list(self.positions)[-n:]
    
    def get_position_at(self, index: int) -> Optional[PositionRecord]:
        """Get position at specific index (0 = oldest)."""
        if 0 <= index < len(self.positions):
            return self.positions[index]
        return None
    
    @property
    def current_position(self) -> Optional[PositionRecord]:
        """Get most recent position."""
        if self.positions:
            return self.positions[-1]
        return None
    
    @property
    def previous_position(self) -> Optional[PositionRecord]:
        """Get second most recent position."""
        if len(self.positions) >= 2:
            return self.positions[-2]
        return None


class TrackHistoryManager:
    """
    Manages time series history for all tracks.
    
    Provides efficient storage and retrieval of track histories
    with automatic sliding window management.
    
    Attributes:
        window_size: Maximum positions to store per track
        histories: Dictionary of track histories by ID
        
    Example:
        >>> manager = TrackHistoryManager(window_size=60)
        >>> manager.update(tracks, frame_id=1, timestamp=0.033)
        >>> history = manager.get_history(track_id=1)
        >>> print(f"Track 1 has {history.history_length} positions")
    """
    
    def __init__(self, window_size: int = 60, stale_threshold: int = 90):
        """
        Initialize the track history manager.
        
        Args:
            window_size: Maximum positions to keep per track
            stale_threshold: Frames without update before track is stale
        """
        self._window_size = window_size
        self._stale_threshold = stale_threshold
        self._histories: Dict[int, TrackHistory] = {}
        self._current_frame: int = 0
        
        logger.info(
            f"TrackHistoryManager initialized with window_size={window_size}, "
            f"stale_threshold={stale_threshold}"
        )
    
    @property
    def window_size(self) -> int:
        """Get the sliding window size."""
        return self._window_size
    
    @property
    def active_track_count(self) -> int:
        """Get number of active tracks."""
        return len(self._histories)
    
    def update(
        self,
        tracks: List[Track],
        frame_id: int,
        timestamp: float
    ) -> None:
        """
        Update histories with new track observations.
        
        Args:
            tracks: List of Track objects from current frame
            frame_id: Current frame number
            timestamp: Current time in seconds
        """
        self._current_frame = frame_id
        updated_ids = set()
        
        for track in tracks:
            # Compute center position
            x1, y1, x2, y2 = track.bbox
            center_x = (x1 + x2) / 2.0
            center_y = (y1 + y2) / 2.0
            
            # Create position record
            position = PositionRecord(
                frame_id=frame_id,
                timestamp=timestamp,
                x=center_x,
                y=center_y,
                bbox=track.bbox,
                class_id=track.class_id,
                class_name=track.class_name
            )
            
            # Update or create history
            if track.track_id in self._histories:
                history = self._histories[track.track_id]
                
                # Compute distance from previous position
                if history.current_position:
                    prev = history.current_position
                    distance = ((center_x - prev.x) ** 2 + 
                               (center_y - prev.y) ** 2) ** 0.5
                    history.total_distance += distance
                
                # Add new position
                history.positions.append(position)
                history.last_seen_frame = frame_id
                history.last_seen_time = timestamp
            else:
                # Create new history with custom maxlen
                history = TrackHistory(
                    track_id=track.track_id,
                    class_id=track.class_id,
                    class_name=track.class_name,
                    positions=deque([position], maxlen=self._window_size),
                    first_seen_frame=frame_id,
                    first_seen_time=timestamp,
                    last_seen_frame=frame_id,
                    last_seen_time=timestamp
                )
                self._histories[track.track_id] = history
                logger.debug(f"Created new track history: ID={track.track_id}")
            
            updated_ids.add(track.track_id)
        
        # Clean up stale tracks periodically
        if frame_id % 30 == 0:  # Every 30 frames
            self._cleanup_stale_tracks()
    
    def get_history(self, track_id: int) -> Optional[TrackHistory]:
        """
        Get history for a specific track.
        
        Args:
            track_id: Track identifier
            
        Returns:
            TrackHistory if found, None otherwise
        """
        return self._histories.get(track_id)
    
    def get_active_track_ids(self) -> List[int]:
        """
        Get IDs of all tracks with recent observations.
        
        Returns:
            List of active track IDs
        """
        active = []
        for track_id, history in self._histories.items():
            if self._current_frame - history.last_seen_frame <= self._stale_threshold:
                active.append(track_id)
        return active
    
    def get_all_histories(self) -> Dict[int, TrackHistory]:
        """
        Get all track histories.
        
        Returns:
            Dictionary of all track histories
        """
        return self._histories.copy()
    
    def get_recently_updated(self, within_frames: int = 1) -> List[TrackHistory]:
        """
        Get histories updated within the last N frames.
        
        Args:
            within_frames: Frame window to consider as "recent"
            
        Returns:
            List of recently updated TrackHistory objects
        """
        recent = []
        for history in self._histories.values():
            if self._current_frame - history.last_seen_frame <= within_frames:
                recent.append(history)
        return recent
    
    def _cleanup_stale_tracks(self) -> int:
        """
        Remove tracks that haven't been updated recently.
        
        Returns:
            Number of tracks removed
        """
        stale_ids = []
        for track_id, history in self._histories.items():
            frames_since_update = self._current_frame - history.last_seen_frame
            if frames_since_update > self._stale_threshold:
                stale_ids.append(track_id)
        
        for track_id in stale_ids:
            del self._histories[track_id]
        
        if stale_ids:
            logger.debug(f"Cleaned up {len(stale_ids)} stale tracks")
        
        return len(stale_ids)
    
    def reset(self) -> None:
        """Clear all track histories."""
        self._histories.clear()
        self._current_frame = 0
        logger.info("Track history manager reset")
    
    def get_statistics(self) -> Dict[str, any]:
        """
        Get statistics about track histories.
        
        Returns:
            Dictionary with history statistics
        """
        if not self._histories:
            return {
                "total_tracks": 0,
                "active_tracks": 0,
                "avg_history_length": 0,
                "max_history_length": 0,
                "avg_duration": 0
            }
        
        active_count = len(self.get_active_track_ids())
        history_lengths = [h.history_length for h in self._histories.values()]
        durations = [h.duration for h in self._histories.values()]
        
        return {
            "total_tracks": len(self._histories),
            "active_tracks": active_count,
            "avg_history_length": sum(history_lengths) / len(history_lengths),
            "max_history_length": max(history_lengths),
            "avg_duration": sum(durations) / len(durations) if durations else 0
        }
    
    def __repr__(self) -> str:
        return (
            f"TrackHistoryManager(window_size={self._window_size}, "
            f"tracks={len(self._histories)}, "
            f"current_frame={self._current_frame})"
        )
