"""
AegisAI - Service KPI Tracker

Tracks key performance indicators for service operations.

Features:
- Service speed metrics
- Table/counter turnover tracking
- Staff efficiency scores
- Hourly/daily aggregations

Copyright 2024 AegisAI Project
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


@dataclass
class ServiceZone:
    """A service point (table, counter, station)."""
    zone_id: str
    name: str
    zone_type: str  # table, counter, station
    polygon: List[Tuple[int, int]]
    capacity: int = 4


@dataclass
class ServiceSession:
    """A single service session at a zone."""
    session_id: str
    zone_id: str
    started: datetime
    ended: Optional[datetime] = None
    customer_count: int = 1
    staff_ids: List[int] = field(default_factory=list)


@dataclass
class KPIMetrics:
    """Key performance indicators."""
    avg_service_time_minutes: float
    avg_turnover_per_hour: float
    total_customers_served: int
    current_occupancy_percent: float
    staff_efficiency_score: float  # 0-100
    busiest_hour: int  # 0-23
    slowest_zone: Optional[str] = None


class ServiceKPITracker:
    """
    Tracks service KPIs for restaurants and retail.
    
    Example:
        >>> tracker = ServiceKPITracker()
        >>> tracker.add_zone(ServiceZone("table1", "Table 1", "table", [...]))
        >>> tracker.start_session("table1", customer_count=2)
        >>> tracker.end_session("table1")
        >>> kpis = tracker.get_kpis()
    """
    
    def __init__(self):
        """Initialize KPI tracker."""
        self._zones: Dict[str, ServiceZone] = {}
        self._active_sessions: Dict[str, ServiceSession] = {}
        self._completed_sessions: List[ServiceSession] = []
        
        # Hourly stats
        self._hourly_customers: Dict[int, int] = defaultdict(int)
        self._hourly_sessions: Dict[int, int] = defaultdict(int)
        
        # Staff tracking
        self._staff_sessions: Dict[int, int] = defaultdict(int)
        
        self._session_counter = 0
        
        logger.info("ServiceKPITracker initialized")
    
    def add_zone(self, zone: ServiceZone) -> None:
        """Add a service zone."""
        self._zones[zone.zone_id] = zone
    
    def start_session(
        self,
        zone_id: str,
        customer_count: int = 1,
        staff_ids: Optional[List[int]] = None
    ) -> Optional[str]:
        """
        Start a service session at a zone.
        
        Args:
            zone_id: Zone where service starts
            customer_count: Number of customers
            staff_ids: Staff assigned to this session
            
        Returns:
            Session ID or None if zone busy/invalid
        """
        if zone_id not in self._zones:
            return None
        
        if zone_id in self._active_sessions:
            return None  # Zone already occupied
        
        self._session_counter += 1
        session_id = f"session_{self._session_counter}"
        
        session = ServiceSession(
            session_id=session_id,
            zone_id=zone_id,
            started=datetime.now(),
            customer_count=customer_count,
            staff_ids=staff_ids or []
        )
        
        self._active_sessions[zone_id] = session
        
        # Track staff
        for staff_id in (staff_ids or []):
            self._staff_sessions[staff_id] += 1
        
        logger.debug(f"Started session {session_id} at {zone_id}")
        return session_id
    
    def end_session(self, zone_id: str) -> Optional[float]:
        """
        End a service session.
        
        Args:
            zone_id: Zone where session ends
            
        Returns:
            Session duration in seconds, or None
        """
        if zone_id not in self._active_sessions:
            return None
        
        session = self._active_sessions.pop(zone_id)
        session.ended = datetime.now()
        
        duration = (session.ended - session.started).total_seconds()
        
        # Track hourly stats
        hour = session.started.hour
        self._hourly_customers[hour] += session.customer_count
        self._hourly_sessions[hour] += 1
        
        self._completed_sessions.append(session)
        
        logger.debug(f"Ended session at {zone_id}, duration: {duration:.1f}s")
        return duration
    
    def update_from_tracks(
        self,
        tracks: List[Dict],
        class_filter: str = "person"
    ) -> None:
        """
        Auto-detect sessions from track data.
        
        Args:
            tracks: List of track dictionaries with track_id, position, class_name
            class_filter: Only process this class
        """
        for track in tracks:
            if track.get("class_name", "").lower() != class_filter:
                continue
            
            position = track.get("position") or track.get("bbox", [0,0,0,0])[:2]
            if isinstance(position, (list, tuple)) and len(position) >= 2:
                zone_id = self._get_zone_for_position((position[0], position[1]))
                
                if zone_id and zone_id not in self._active_sessions:
                    # Start new session
                    self.start_session(zone_id, customer_count=1)
    
    def _get_zone_for_position(self, position: Tuple[int, int]) -> Optional[str]:
        """Get zone for a position."""
        for zone_id, zone in self._zones.items():
            if self._point_in_polygon(position, zone.polygon):
                return zone_id
        return None
    
    def _point_in_polygon(self, point: Tuple[int, int], polygon: List[Tuple[int, int]]) -> bool:
        """Ray casting test."""
        x, y = point
        n = len(polygon)
        inside = False
        p1x, p1y = polygon[0]
        for i in range(1, n + 1):
            p2x, p2y = polygon[i % n]
            if y > min(p1y, p2y) and y <= max(p1y, p2y) and x <= max(p1x, p2x):
                if p1y != p2y:
                    xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                if p1x == p2x or x <= xinters:
                    inside = not inside
            p1x, p1y = p2x, p2y
        return inside
    
    def get_kpis(self) -> KPIMetrics:
        """Calculate current KPIs."""
        # Service time
        service_times = [
            (s.ended - s.started).total_seconds() / 60
            for s in self._completed_sessions
            if s.ended
        ]
        avg_service = sum(service_times) / len(service_times) if service_times else 0
        
        # Turnover
        hours_tracked = len(set(s.started.hour for s in self._completed_sessions)) or 1
        turnover = len(self._completed_sessions) / hours_tracked
        
        # Customers served
        total_customers = sum(s.customer_count for s in self._completed_sessions)
        
        # Occupancy
        occupied = len(self._active_sessions)
        total = len(self._zones) or 1
        occupancy = (occupied / total) * 100
        
        # Staff efficiency (sessions per staff member)
        if self._staff_sessions:
            avg_per_staff = sum(self._staff_sessions.values()) / len(self._staff_sessions)
            efficiency = min(100, avg_per_staff * 20)  # Scale to 100
        else:
            efficiency = 50.0
        
        # Busiest hour
        busiest = max(self._hourly_customers.items(), key=lambda x: x[1], default=(12, 0))[0]
        
        # Slowest zone
        zone_times: Dict[str, List[float]] = defaultdict(list)
        for s in self._completed_sessions:
            if s.ended:
                zone_times[s.zone_id].append((s.ended - s.started).total_seconds())
        
        slowest = None
        if zone_times:
            avg_times = {z: sum(t)/len(t) for z, t in zone_times.items()}
            slowest = max(avg_times.items(), key=lambda x: x[1])[0]
        
        return KPIMetrics(
            avg_service_time_minutes=round(avg_service, 1),
            avg_turnover_per_hour=round(turnover, 1),
            total_customers_served=total_customers,
            current_occupancy_percent=round(occupancy, 1),
            staff_efficiency_score=round(efficiency, 1),
            busiest_hour=busiest,
            slowest_zone=slowest
        )
    
    def get_metrics(self) -> Dict:
        """Get all metrics as dictionary."""
        kpis = self.get_kpis()
        return {
            "kpis": kpis.__dict__,
            "active_sessions": len(self._active_sessions),
            "completed_sessions": len(self._completed_sessions),
            "zones": len(self._zones),
            "hourly_distribution": dict(self._hourly_customers)
        }
