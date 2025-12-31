"""
AegisAI - Smart City Risk Intelligence System
Analysis Module - Shared Types

This module defines all shared data structures for the Analysis Layer.
These types provide standardized containers for motion, behavior, and crowd analysis.

Phase 2: Analysis Layer
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict
from enum import Enum, auto
import math


class BehaviorType(Enum):
    """Enumeration of detectable behavior types."""
    NORMAL = auto()
    STATIONARY = auto()
    LOITERING = auto()
    SUDDEN_SPEED_CHANGE = auto()
    DIRECTION_REVERSAL = auto()
    ERRATIC_MOTION = auto()
    RUNNING = auto()


@dataclass
class PositionRecord:
    """
    A single position observation for a track.
    
    Attributes:
        frame_id: Frame number when observed
        timestamp: Time in seconds since video start
        x: Center x-coordinate in pixels
        y: Center y-coordinate in pixels
        bbox: Full bounding box (x1, y1, x2, y2)
        class_id: Object class identifier
        class_name: Human-readable class name
    """
    frame_id: int
    timestamp: float
    x: float
    y: float
    bbox: Tuple[int, int, int, int]
    class_id: int
    class_name: str


@dataclass
class MotionState:
    """
    Motion metrics for a single track at current frame.
    
    Attributes:
        speed: Instantaneous speed in pixels per frame
        speed_smoothed: Smoothed speed over recent frames
        velocity: Velocity vector (dx, dy) in pixels per frame
        direction: Movement direction in radians (0=right, π/2=up)
        acceleration: Change in speed from previous frame
        is_moving: Whether the object is considered moving
        distance_traveled: Total distance traveled since track creation
    """
    speed: float = 0.0
    speed_smoothed: float = 0.0
    velocity: Tuple[float, float] = (0.0, 0.0)
    direction: float = 0.0
    acceleration: float = 0.0
    is_moving: bool = False
    distance_traveled: float = 0.0
    
    @property
    def direction_degrees(self) -> float:
        """Get direction in degrees (0-360, clockwise from right)."""
        degrees = math.degrees(self.direction)
        return (360 - degrees) % 360


@dataclass
class BehaviorFlags:
    """
    Boolean flags indicating detected behaviors for a track.
    
    Attributes:
        is_stationary: Object has very low speed
        is_loitering: Object stationary for extended period
        sudden_speed_change: Significant speed change detected
        direction_reversal: Object reversed direction (>135°)
        is_erratic: High variance in motion direction
        is_running: Speed exceeds running threshold (persons only)
        anomaly_score: Composite anomaly score (0-1)
    """
    is_stationary: bool = False
    is_loitering: bool = False
    sudden_speed_change: bool = False
    direction_reversal: bool = False
    is_erratic: bool = False
    is_running: bool = False
    anomaly_score: float = 0.0
    
    @property
    def has_anomaly(self) -> bool:
        """Check if any anomaly flag is set."""
        return (
            self.is_loitering or 
            self.sudden_speed_change or 
            self.direction_reversal or 
            self.is_erratic
        )
    
    @property
    def active_behaviors(self) -> List[BehaviorType]:
        """Get list of currently active behavior types."""
        behaviors = []
        if self.is_stationary:
            behaviors.append(BehaviorType.STATIONARY)
        if self.is_loitering:
            behaviors.append(BehaviorType.LOITERING)
        if self.sudden_speed_change:
            behaviors.append(BehaviorType.SUDDEN_SPEED_CHANGE)
        if self.direction_reversal:
            behaviors.append(BehaviorType.DIRECTION_REVERSAL)
        if self.is_erratic:
            behaviors.append(BehaviorType.ERRATIC_MOTION)
        if self.is_running:
            behaviors.append(BehaviorType.RUNNING)
        if not behaviors:
            behaviors.append(BehaviorType.NORMAL)
        return behaviors


@dataclass
class TrackAnalysis:
    """
    Complete analysis result for a single track.
    
    Attributes:
        track_id: Unique identifier for this track
        class_id: Object class identifier
        class_name: Human-readable class name
        motion: Current motion state
        behavior: Current behavior flags
        history_length: Number of frames in track history
        time_tracked: Total time tracked in seconds
        current_position: Current (x, y) position
        current_bbox: Current bounding box
    """
    track_id: int
    class_id: int
    class_name: str
    motion: MotionState
    behavior: BehaviorFlags
    history_length: int
    time_tracked: float
    current_position: Tuple[float, float]
    current_bbox: Tuple[int, int, int, int]


@dataclass
class DensityCell:
    """
    A single cell in the density grid.
    
    Attributes:
        row: Grid row index
        col: Grid column index
        count: Number of objects in this cell
        center_x: Cell center x-coordinate
        center_y: Cell center y-coordinate
    """
    row: int
    col: int
    count: int
    center_x: float
    center_y: float


@dataclass
class CrowdMetrics:
    """
    Frame-level crowd and density metrics.
    
    Attributes:
        person_count: Number of active person tracks
        vehicle_count: Number of active vehicle tracks
        total_count: Total number of active tracks
        density_map: 2D grid of object counts
        hotspots: List of high-density cells
        max_density: Maximum density in any cell
        average_density: Average density across all cells
        density_variance: Variance in density distribution
        crowd_detected: Whether crowd threshold is exceeded
    """
    person_count: int = 0
    vehicle_count: int = 0
    total_count: int = 0
    density_map: List[List[int]] = field(default_factory=list)
    hotspots: List[DensityCell] = field(default_factory=list)
    max_density: int = 0
    average_density: float = 0.0
    density_variance: float = 0.0
    crowd_detected: bool = False


@dataclass
class FrameAnalysis:
    """
    Aggregated analysis result for an entire frame.
    
    Attributes:
        frame_id: Frame number
        timestamp: Time in seconds since video start
        track_analyses: Analysis results for all active tracks
        crowd_metrics: Frame-level crowd statistics
        anomaly_count: Number of tracks with anomalies
        anomaly_tracks: List of track IDs with anomalies
    """
    frame_id: int
    timestamp: float
    track_analyses: List[TrackAnalysis] = field(default_factory=list)
    crowd_metrics: CrowdMetrics = field(default_factory=CrowdMetrics)
    anomaly_count: int = 0
    anomaly_tracks: List[int] = field(default_factory=list)
    
    def get_track_analysis(self, track_id: int) -> Optional[TrackAnalysis]:
        """Get analysis for a specific track ID."""
        for ta in self.track_analyses:
            if ta.track_id == track_id:
                return ta
        return None
    
    @property
    def has_anomalies(self) -> bool:
        """Check if any anomalies were detected in this frame."""
        return self.anomaly_count > 0
