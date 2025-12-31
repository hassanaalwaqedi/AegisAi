"""
AegisAI - Smart City Risk Intelligence System
API Module - Shared State

This module provides thread-safe shared state for the API.
Stores current system status, tracks, and events.

Phase 4: Response & Productization Layer
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from collections import deque


@dataclass
class SystemStatus:
    """
    Current system status.
    
    Attributes:
        running: Whether processing is active
        start_time: When system started
        frames_processed: Total frames processed
        current_fps: Current processing FPS
        active_tracks: Number of active tracks
        total_detections: Total detections count
        total_anomalies: Total anomalies detected
        max_risk_level: Highest current risk level
    """
    running: bool = False
    start_time: Optional[datetime] = None
    frames_processed: int = 0
    current_fps: float = 0.0
    active_tracks: int = 0
    total_detections: int = 0
    total_anomalies: int = 0
    max_risk_level: str = "LOW"
    max_risk_score: float = 0.0
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        uptime = 0
        if self.start_time:
            uptime = (datetime.now() - self.start_time).total_seconds()
        
        return {
            "running": self.running,
            "uptime_seconds": round(uptime, 1),
            "frames_processed": self.frames_processed,
            "current_fps": round(self.current_fps, 1),
            "active_tracks": self.active_tracks,
            "total_detections": self.total_detections,
            "total_anomalies": self.total_anomalies,
            "max_risk_level": self.max_risk_level,
            "max_risk_score": round(self.max_risk_score, 3)
        }


@dataclass
class TrackInfo:
    """
    Information about an active track.
    
    Attributes:
        track_id: Unique track identifier
        class_name: Object class (Person, Car, etc.)
        risk_level: Current risk level
        risk_score: Current risk score
        zone: Current zone
        behaviors: Active behaviors
        time_tracked: Duration tracked
    """
    track_id: int
    class_name: str = "Unknown"
    risk_level: str = "LOW"
    risk_score: float = 0.0
    zone: str = ""
    behaviors: List[str] = field(default_factory=list)
    time_tracked: float = 0.0
    last_updated: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "track_id": self.track_id,
            "class_name": self.class_name,
            "risk_level": self.risk_level,
            "risk_score": round(self.risk_score, 3),
            "zone": self.zone,
            "behaviors": self.behaviors,
            "time_tracked": round(self.time_tracked, 1)
        }


class APIState:
    """
    Thread-safe shared state for the API.
    
    Stores current system status, active tracks, events, and statistics.
    All access is protected by a lock for thread safety.
    
    Example:
        >>> state = APIState()
        >>> state.update_status(frames=100, fps=30.0)
        >>> status = state.get_status()
    """
    
    def __init__(self):
        """Initialize API state."""
        self._lock = threading.RLock()
        self._status = SystemStatus()
        self._tracks: Dict[int, TrackInfo] = {}
        self._events: deque = deque(maxlen=100)
        self._statistics: Dict[str, Any] = {}
    
    def start(self) -> None:
        """Mark system as started."""
        with self._lock:
            self._status.running = True
            self._status.start_time = datetime.now()
    
    def stop(self) -> None:
        """Mark system as stopped."""
        with self._lock:
            self._status.running = False
    
    def update_status(
        self,
        frames: Optional[int] = None,
        fps: Optional[float] = None,
        active_tracks: Optional[int] = None,
        detections: Optional[int] = None,
        anomalies: Optional[int] = None,
        max_risk_level: Optional[str] = None,
        max_risk_score: Optional[float] = None
    ) -> None:
        """
        Update system status.
        
        Args:
            frames: Frames processed
            fps: Current FPS
            active_tracks: Active track count
            detections: Total detections
            anomalies: Total anomalies
            max_risk_level: Highest risk level
            max_risk_score: Highest risk score
        """
        with self._lock:
            if frames is not None:
                self._status.frames_processed = frames
            if fps is not None:
                self._status.current_fps = fps
            if active_tracks is not None:
                self._status.active_tracks = active_tracks
            if detections is not None:
                self._status.total_detections = detections
            if anomalies is not None:
                self._status.total_anomalies = anomalies
            if max_risk_level is not None:
                self._status.max_risk_level = max_risk_level
            if max_risk_score is not None:
                self._status.max_risk_score = max_risk_score
    
    def get_status(self) -> dict:
        """Get current system status as dictionary."""
        with self._lock:
            return self._status.to_dict()
    
    def update_track(
        self,
        track_id: int,
        class_name: str = "Unknown",
        risk_level: str = "LOW",
        risk_score: float = 0.0,
        zone: str = "",
        behaviors: Optional[List[str]] = None,
        time_tracked: float = 0.0
    ) -> None:
        """Update or add a track."""
        with self._lock:
            self._tracks[track_id] = TrackInfo(
                track_id=track_id,
                class_name=class_name,
                risk_level=risk_level,
                risk_score=risk_score,
                zone=zone,
                behaviors=behaviors or [],
                time_tracked=time_tracked,
                last_updated=datetime.now()
            )
    
    def remove_track(self, track_id: int) -> None:
        """Remove a track."""
        with self._lock:
            if track_id in self._tracks:
                del self._tracks[track_id]
    
    def get_tracks(self, min_risk_level: Optional[str] = None) -> List[dict]:
        """
        Get active tracks.
        
        Args:
            min_risk_level: Filter by minimum risk level
            
        Returns:
            List of track dictionaries
        """
        level_priority = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
        min_priority = level_priority.get(min_risk_level, 0) if min_risk_level else 0
        
        with self._lock:
            tracks = []
            for track in self._tracks.values():
                track_priority = level_priority.get(track.risk_level, 0)
                if track_priority >= min_priority:
                    tracks.append(track.to_dict())
            return sorted(tracks, key=lambda t: -t["risk_score"])
    
    def add_event(self, event: dict) -> None:
        """Add an event to the event log."""
        with self._lock:
            self._events.append(event)
    
    def get_events(self, limit: int = 20) -> List[dict]:
        """Get recent events."""
        with self._lock:
            return list(self._events)[-limit:]
    
    def update_statistics(
        self,
        person_count: int = 0,
        vehicle_count: int = 0,
        crowd_detected: bool = False,
        max_density: int = 0,
        risk_distribution: Optional[Dict[str, int]] = None
    ) -> None:
        """Update crowd and risk statistics."""
        with self._lock:
            self._statistics = {
                "person_count": person_count,
                "vehicle_count": vehicle_count,
                "crowd_detected": crowd_detected,
                "max_density": max_density,
                "risk_distribution": risk_distribution or {
                    "LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0
                },
                "timestamp": datetime.now().isoformat()
            }
    
    def get_statistics(self) -> dict:
        """Get current statistics."""
        with self._lock:
            return self._statistics.copy()
    
    def cleanup_stale_tracks(self, max_age_seconds: float = 5.0) -> int:
        """Remove tracks not updated recently."""
        with self._lock:
            now = datetime.now()
            stale = [
                tid for tid, track in self._tracks.items()
                if (now - track.last_updated).total_seconds() > max_age_seconds
            ]
            for tid in stale:
                del self._tracks[tid]
            return len(stale)
    
    def reset(self) -> None:
        """Reset all state."""
        with self._lock:
            self._status = SystemStatus()
            self._tracks.clear()
            self._events.clear()
            self._statistics.clear()


# Global singleton instance
_state: Optional[APIState] = None


def get_state() -> APIState:
    """Get the global API state singleton."""
    global _state
    if _state is None:
        _state = APIState()
    return _state
