"""
AegisAI - Queue Analyzer

Detects and analyzes customer queues in retail/restaurant environments.

Features:
- Queue detection and line tracking
- Wait time estimation
- Queue length monitoring
- Service rate calculation

Copyright 2024 AegisAI Project
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import deque
import logging

logger = logging.getLogger(__name__)


@dataclass
class QueueZone:
    """Definition of a queue detection zone."""
    zone_id: str
    name: str
    polygon: List[Tuple[int, int]]
    queue_direction: str = "vertical"  # vertical, horizontal
    max_capacity: int = 20


@dataclass
class QueueMember:
    """A person in the queue."""
    track_id: int
    entered_queue: datetime
    position_in_line: int
    position: Tuple[int, int]
    wait_time_seconds: float = 0.0


@dataclass
class QueueStatus:
    """Current status of a queue."""
    zone_id: str
    zone_name: str
    current_length: int
    avg_wait_time_seconds: float
    max_wait_time_seconds: float
    estimated_wait_minutes: float
    is_busy: bool
    capacity_percent: float
    members: List[QueueMember]


class QueueAnalyzer:
    """
    Analyzes customer queues for wait times and service metrics.
    
    Example:
        >>> analyzer = QueueAnalyzer()
        >>> analyzer.add_queue_zone(QueueZone("checkout", "Checkout Line", [...]))
        >>> analyzer.update(track_id=5, position=(100, 200), class_name="person")
        >>> status = analyzer.get_queue_status("checkout")
    """
    
    def __init__(
        self,
        busy_threshold: int = 5,
        service_rate_window: int = 10
    ):
        """
        Initialize queue analyzer.
        
        Args:
            busy_threshold: Queue length to mark as busy
            service_rate_window: Number of recent services to average
        """
        self._zones: Dict[str, QueueZone] = {}
        self._queues: Dict[str, Dict[int, QueueMember]] = {}
        self._busy_threshold = busy_threshold
        
        # Service rate tracking
        self._service_times: Dict[str, deque] = {}
        self._service_window = service_rate_window
        
        # Stats
        self._total_served: Dict[str, int] = {}
        self._total_wait_time: Dict[str, float] = {}
        
        logger.info("QueueAnalyzer initialized")
    
    def add_queue_zone(self, zone: QueueZone) -> None:
        """Add a queue detection zone."""
        self._zones[zone.zone_id] = zone
        self._queues[zone.zone_id] = {}
        self._service_times[zone.zone_id] = deque(maxlen=self._service_window)
        self._total_served[zone.zone_id] = 0
        self._total_wait_time[zone.zone_id] = 0.0
    
    def update(
        self,
        track_id: int,
        position: Tuple[int, int],
        class_name: str = "person"
    ) -> None:
        """
        Update queue with new track position.
        
        Args:
            track_id: Unique track identifier
            position: (x, y) position
            class_name: Must be "person"
        """
        if class_name.lower() != "person":
            return
        
        # Check which queue zone the person is in
        queue_zone = self._get_zone_for_position(position)
        
        if queue_zone:
            # Person is in a queue zone
            if track_id not in self._queues[queue_zone]:
                # New person entering queue
                self._queues[queue_zone][track_id] = QueueMember(
                    track_id=track_id,
                    entered_queue=datetime.now(),
                    position_in_line=len(self._queues[queue_zone]) + 1,
                    position=position
                )
            else:
                # Update existing position
                member = self._queues[queue_zone][track_id]
                member.position = position
                member.wait_time_seconds = (datetime.now() - member.entered_queue).total_seconds()
        else:
            # Person left all queue zones - check if they were in one
            for zone_id, queue in self._queues.items():
                if track_id in queue:
                    # Person left queue (served)
                    member = queue[track_id]
                    wait_time = (datetime.now() - member.entered_queue).total_seconds()
                    
                    self._service_times[zone_id].append(wait_time)
                    self._total_served[zone_id] += 1
                    self._total_wait_time[zone_id] += wait_time
                    
                    del queue[track_id]
                    self._reorder_queue(zone_id)
                    break
    
    def remove_track(self, track_id: int) -> None:
        """Remove a track from all queues."""
        for queue in self._queues.values():
            if track_id in queue:
                del queue[track_id]
    
    def _get_zone_for_position(self, position: Tuple[int, int]) -> Optional[str]:
        """Get queue zone for a position."""
        for zone_id, zone in self._zones.items():
            if self._point_in_polygon(position, zone.polygon):
                return zone_id
        return None
    
    def _point_in_polygon(self, point: Tuple[int, int], polygon: List[Tuple[int, int]]) -> bool:
        """Ray casting point-in-polygon test."""
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
    
    def _reorder_queue(self, zone_id: str) -> None:
        """Reorder queue positions after someone leaves."""
        zone = self._zones.get(zone_id)
        if not zone:
            return
        
        members = list(self._queues[zone_id].values())
        
        # Sort by position based on queue direction
        if zone.queue_direction == "vertical":
            members.sort(key=lambda m: m.position[1])  # Top to bottom
        else:
            members.sort(key=lambda m: m.position[0])  # Left to right
        
        for i, member in enumerate(members):
            member.position_in_line = i + 1
    
    def get_queue_status(self, zone_id: str) -> Optional[QueueStatus]:
        """Get status of a specific queue."""
        if zone_id not in self._zones:
            return None
        
        zone = self._zones[zone_id]
        queue = self._queues[zone_id]
        
        members = list(queue.values())
        current_length = len(members)
        
        # Calculate wait times
        wait_times = [m.wait_time_seconds for m in members]
        avg_wait = sum(wait_times) / len(wait_times) if wait_times else 0
        max_wait = max(wait_times) if wait_times else 0
        
        # Estimate wait for new person
        recent_service = list(self._service_times[zone_id])
        avg_service = sum(recent_service) / len(recent_service) if recent_service else 60
        estimated_wait = (current_length * avg_service) / 60  # minutes
        
        return QueueStatus(
            zone_id=zone_id,
            zone_name=zone.name,
            current_length=current_length,
            avg_wait_time_seconds=avg_wait,
            max_wait_time_seconds=max_wait,
            estimated_wait_minutes=round(estimated_wait, 1),
            is_busy=current_length >= self._busy_threshold,
            capacity_percent=min(100, (current_length / zone.max_capacity) * 100),
            members=members
        )
    
    def get_all_queues_status(self) -> List[QueueStatus]:
        """Get status of all queues."""
        return [
            self.get_queue_status(zone_id)
            for zone_id in self._zones.keys()
        ]
    
    def get_metrics(self) -> Dict:
        """Get overall queue metrics."""
        total_waiting = sum(len(q) for q in self._queues.values())
        all_wait_times = []
        
        for queue in self._queues.values():
            for member in queue.values():
                all_wait_times.append(member.wait_time_seconds)
        
        return {
            "total_queues": len(self._zones),
            "total_waiting": total_waiting,
            "avg_wait_seconds": sum(all_wait_times) / len(all_wait_times) if all_wait_times else 0,
            "total_served_today": sum(self._total_served.values()),
            "queues": [s.__dict__ for s in self.get_all_queues_status() if s]
        }
