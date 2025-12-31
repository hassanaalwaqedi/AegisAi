"""
AegisAI - Employee Monitor

Tracks staff positions, movement patterns, and coverage analysis.
Designed for restaurant, retail, and service environments.

Features:
- Staff position tracking (anonymous by track ID)
- Zone coverage analysis
- Idle time detection
- Movement heatmap generation

Copyright 2024 AegisAI Project
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set
from datetime import datetime, timedelta
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


@dataclass
class StaffZone:
    """Definition of a staff coverage zone."""
    zone_id: str
    name: str
    polygon: List[Tuple[int, int]]  # [(x1,y1), (x2,y2), ...]
    min_coverage: int = 1  # Minimum staff required
    priority: str = "normal"  # low, normal, high, critical


@dataclass
class StaffPosition:
    """Current position and state of a staff member."""
    track_id: int
    position: Tuple[int, int]
    zone_id: Optional[str] = None
    idle_time: float = 0.0
    last_movement: datetime = field(default_factory=datetime.now)
    total_distance: float = 0.0
    positions_history: List[Tuple[int, int]] = field(default_factory=list)


@dataclass
class CoverageMetrics:
    """Zone coverage analysis results."""
    zone_id: str
    zone_name: str
    current_staff: int
    required_staff: int
    is_covered: bool
    coverage_percent: float
    staff_ids: List[int]


class EmployeeMonitor:
    """
    Monitors staff positions and analyzes coverage.
    
    Example:
        >>> monitor = EmployeeMonitor()
        >>> monitor.add_zone(StaffZone("kitchen", "Kitchen", [(0,0), (100,0), (100,100), (0,100)]))
        >>> monitor.update_staff(track_id=1, position=(50, 50), class_name="person")
        >>> coverage = monitor.get_zone_coverage()
    """
    
    def __init__(
        self,
        idle_threshold_seconds: float = 30.0,
        position_history_size: int = 100,
        movement_threshold_pixels: float = 10.0
    ):
        """
        Initialize employee monitor.
        
        Args:
            idle_threshold_seconds: Time before marking as idle
            position_history_size: Max positions to track per staff
            movement_threshold_pixels: Min movement to count as active
        """
        self._zones: Dict[str, StaffZone] = {}
        self._staff: Dict[int, StaffPosition] = {}
        self._idle_threshold = idle_threshold_seconds
        self._history_size = position_history_size
        self._movement_threshold = movement_threshold_pixels
        
        # Metrics
        self._total_staff_seen = 0
        self._zone_time: Dict[str, Dict[int, float]] = defaultdict(lambda: defaultdict(float))
        
        logger.info(f"EmployeeMonitor initialized (idle_threshold={idle_threshold_seconds}s)")
    
    def add_zone(self, zone: StaffZone) -> None:
        """Add a coverage zone."""
        self._zones[zone.zone_id] = zone
        logger.debug(f"Added zone: {zone.name}")
    
    def remove_zone(self, zone_id: str) -> None:
        """Remove a coverage zone."""
        if zone_id in self._zones:
            del self._zones[zone_id]
    
    def update_staff(
        self,
        track_id: int,
        position: Tuple[int, int],
        class_name: str = "person"
    ) -> Optional[StaffPosition]:
        """
        Update staff position.
        
        Args:
            track_id: Unique track identifier
            position: (x, y) position
            class_name: Object class (must be "person")
            
        Returns:
            Updated StaffPosition or None if not a person
        """
        if class_name.lower() != "person":
            return None
        
        now = datetime.now()
        
        if track_id in self._staff:
            staff = self._staff[track_id]
            old_pos = staff.position
            
            # Calculate movement
            dx = position[0] - old_pos[0]
            dy = position[1] - old_pos[1]
            distance = (dx**2 + dy**2) ** 0.5
            
            if distance > self._movement_threshold:
                staff.last_movement = now
                staff.total_distance += distance
            else:
                # Check for idle
                idle_seconds = (now - staff.last_movement).total_seconds()
                staff.idle_time = idle_seconds
            
            # Update position
            staff.position = position
            staff.positions_history.append(position)
            if len(staff.positions_history) > self._history_size:
                staff.positions_history.pop(0)
            
            # Update zone
            staff.zone_id = self._get_zone_for_position(position)
            
        else:
            # New staff member
            self._total_staff_seen += 1
            self._staff[track_id] = StaffPosition(
                track_id=track_id,
                position=position,
                zone_id=self._get_zone_for_position(position),
                positions_history=[position]
            )
        
        return self._staff[track_id]
    
    def remove_staff(self, track_id: int) -> None:
        """Remove a staff member from tracking."""
        if track_id in self._staff:
            del self._staff[track_id]
    
    def _get_zone_for_position(self, position: Tuple[int, int]) -> Optional[str]:
        """Determine which zone a position is in."""
        for zone_id, zone in self._zones.items():
            if self._point_in_polygon(position, zone.polygon):
                return zone_id
        return None
    
    def _point_in_polygon(self, point: Tuple[int, int], polygon: List[Tuple[int, int]]) -> bool:
        """Check if point is inside polygon (ray casting)."""
        x, y = point
        n = len(polygon)
        inside = False
        
        p1x, p1y = polygon[0]
        for i in range(1, n + 1):
            p2x, p2y = polygon[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        
        return inside
    
    def get_zone_coverage(self) -> List[CoverageMetrics]:
        """Get coverage metrics for all zones."""
        coverage = []
        
        for zone_id, zone in self._zones.items():
            staff_in_zone = [
                s.track_id for s in self._staff.values()
                if s.zone_id == zone_id
            ]
            
            current = len(staff_in_zone)
            required = zone.min_coverage
            
            coverage.append(CoverageMetrics(
                zone_id=zone_id,
                zone_name=zone.name,
                current_staff=current,
                required_staff=required,
                is_covered=current >= required,
                coverage_percent=min(100.0, (current / max(1, required)) * 100),
                staff_ids=staff_in_zone
            ))
        
        return coverage
    
    def get_idle_staff(self) -> List[StaffPosition]:
        """Get list of idle staff members."""
        return [
            s for s in self._staff.values()
            if s.idle_time >= self._idle_threshold
        ]
    
    def get_active_staff_count(self) -> int:
        """Get count of active (non-idle) staff."""
        return sum(
            1 for s in self._staff.values()
            if s.idle_time < self._idle_threshold
        )
    
    def get_staff_heatmap_data(self, grid_size: int = 50) -> List[Dict]:
        """
        Generate heatmap data from staff positions.
        
        Returns:
            List of {x, y, density} for heatmap visualization
        """
        position_counts: Dict[Tuple[int, int], int] = defaultdict(int)
        
        for staff in self._staff.values():
            for pos in staff.positions_history:
                grid_x = pos[0] // grid_size
                grid_y = pos[1] // grid_size
                position_counts[(grid_x, grid_y)] += 1
        
        if not position_counts:
            return []
        
        max_count = max(position_counts.values())
        
        return [
            {"x": x, "y": y, "density": count / max_count}
            for (x, y), count in position_counts.items()
        ]
    
    def get_metrics(self) -> Dict:
        """Get overall monitoring metrics."""
        active = self.get_active_staff_count()
        idle = len(self.get_idle_staff())
        
        return {
            "total_staff_tracked": len(self._staff),
            "active_staff": active,
            "idle_staff": idle,
            "total_staff_seen": self._total_staff_seen,
            "zones_defined": len(self._zones),
            "coverage": [c.__dict__ for c in self.get_zone_coverage()]
        }
