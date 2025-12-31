"""
AegisAI - Smart City Risk Intelligence System
Zone Context Module

This module provides zone-based risk weighting for context-aware decisions.
Supports restricted zones, high-risk areas, and normal zones.

Features:
- Rectangle-based zone definitions
- Configurable risk multipliers per zone type
- Track position zone detection
- Zone overlap handling

Phase 3: Risk Intelligence Layer
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

# Configure module logger
logger = logging.getLogger(__name__)


class ZoneType(Enum):
    """
    Zone classification types with risk implications.
    
    Attributes:
        NORMAL: Standard monitoring area
        ELEVATED: Slightly elevated risk area
        HIGH_RISK: Known high-risk location
        RESTRICTED: Restricted/forbidden area
    """
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    HIGH_RISK = "HIGH_RISK"
    RESTRICTED = "RESTRICTED"
    
    @property
    def default_multiplier(self) -> float:
        """Get default risk multiplier for this zone type."""
        multipliers = {
            ZoneType.NORMAL: 1.0,
            ZoneType.ELEVATED: 1.25,
            ZoneType.HIGH_RISK: 1.5,
            ZoneType.RESTRICTED: 2.0
        }
        return multipliers.get(self, 1.0)


@dataclass
class Zone:
    """
    A defined zone with risk implications.
    
    Attributes:
        zone_id: Unique identifier
        name: Human-readable name
        zone_type: Type of zone (affects risk multiplier)
        bounds: Rectangle bounds (x1, y1, x2, y2) in pixels
        multiplier: Custom risk multiplier (overrides default)
        description: Optional zone description
        active: Whether zone is currently active
    """
    zone_id: str
    name: str
    zone_type: ZoneType
    bounds: Tuple[int, int, int, int]  # x1, y1, x2, y2
    multiplier: Optional[float] = None
    description: str = ""
    active: bool = True
    
    @property
    def risk_multiplier(self) -> float:
        """Get effective risk multiplier."""
        if self.multiplier is not None:
            return self.multiplier
        return self.zone_type.default_multiplier
    
    def contains_point(self, x: float, y: float) -> bool:
        """
        Check if a point is within this zone.
        
        Args:
            x: X coordinate
            y: Y coordinate
            
        Returns:
            True if point is within zone bounds
        """
        if not self.active:
            return False
        x1, y1, x2, y2 = self.bounds
        return x1 <= x <= x2 and y1 <= y <= y2
    
    def contains_bbox(self, bbox: Tuple[int, int, int, int]) -> bool:
        """
        Check if a bounding box center is within this zone.
        
        Args:
            bbox: Bounding box (x1, y1, x2, y2)
            
        Returns:
            True if bbox center is within zone
        """
        bx1, by1, bx2, by2 = bbox
        center_x = (bx1 + bx2) / 2
        center_y = (by1 + by2) / 2
        return self.contains_point(center_x, center_y)


@dataclass
class ZoneContext:
    """
    Context information for a position/track regarding zones.
    
    Attributes:
        in_zone: Whether position is in any defined zone
        zone: The zone containing the position (if any)
        zone_type: Type of the containing zone
        multiplier: Effective risk multiplier
    """
    in_zone: bool = False
    zone: Optional[Zone] = None
    zone_type: ZoneType = ZoneType.NORMAL
    multiplier: float = 1.0
    
    @property
    def zone_name(self) -> str:
        """Get zone name or 'Normal Area'."""
        if self.zone:
            return self.zone.name
        return "Normal Area"


class ZoneManager:
    """
    Manages zone definitions and provides zone context lookups.
    
    Attributes:
        zones: Dictionary of zone_id to Zone
        
    Example:
        >>> manager = ZoneManager()
        >>> manager.add_zone(Zone(
        ...     zone_id="restricted_1",
        ...     name="Server Room Entrance",
        ...     zone_type=ZoneType.RESTRICTED,
        ...     bounds=(100, 100, 300, 300)
        ... ))
        >>> context = manager.get_context(bbox=(150, 150, 200, 200))
        >>> print(f"Multiplier: {context.multiplier}")
    """
    
    def __init__(self):
        """Initialize the zone manager."""
        self._zones: Dict[str, Zone] = {}
        self._default_context = ZoneContext()
        logger.info("ZoneManager initialized")
    
    @property
    def zone_count(self) -> int:
        """Get number of defined zones."""
        return len(self._zones)
    
    def add_zone(self, zone: Zone) -> None:
        """
        Add a zone definition.
        
        Args:
            zone: Zone to add
        """
        self._zones[zone.zone_id] = zone
        logger.debug(f"Added zone: {zone.name} ({zone.zone_type.value})")
    
    def remove_zone(self, zone_id: str) -> bool:
        """
        Remove a zone definition.
        
        Args:
            zone_id: ID of zone to remove
            
        Returns:
            True if zone was removed
        """
        if zone_id in self._zones:
            del self._zones[zone_id]
            return True
        return False
    
    def get_zone(self, zone_id: str) -> Optional[Zone]:
        """Get a zone by ID."""
        return self._zones.get(zone_id)
    
    def get_all_zones(self) -> List[Zone]:
        """Get all defined zones."""
        return list(self._zones.values())
    
    def get_context(
        self,
        position: Optional[Tuple[float, float]] = None,
        bbox: Optional[Tuple[int, int, int, int]] = None
    ) -> ZoneContext:
        """
        Get zone context for a position or bounding box.
        
        Args:
            position: (x, y) coordinate
            bbox: Bounding box (x1, y1, x2, y2)
            
        Returns:
            ZoneContext with zone information
        """
        # Determine check point
        if position:
            x, y = position
        elif bbox:
            x = (bbox[0] + bbox[2]) / 2
            y = (bbox[1] + bbox[3]) / 2
        else:
            return self._default_context
        
        # Find highest-priority zone containing point
        # Priority: RESTRICTED > HIGH_RISK > ELEVATED > NORMAL
        priority_order = [
            ZoneType.RESTRICTED,
            ZoneType.HIGH_RISK,
            ZoneType.ELEVATED,
            ZoneType.NORMAL
        ]
        
        for zone_type in priority_order:
            for zone in self._zones.values():
                if zone.zone_type == zone_type and zone.contains_point(x, y):
                    return ZoneContext(
                        in_zone=True,
                        zone=zone,
                        zone_type=zone.zone_type,
                        multiplier=zone.risk_multiplier
                    )
        
        return self._default_context
    
    def add_sample_zones(self, frame_width: int, frame_height: int) -> None:
        """
        Add sample zones for testing/demonstration.
        
        Args:
            frame_width: Video frame width
            frame_height: Video frame height
        """
        # Example: Restricted zone in top-left corner
        self.add_zone(Zone(
            zone_id="restricted_demo",
            name="Restricted Area",
            zone_type=ZoneType.RESTRICTED,
            bounds=(0, 0, frame_width // 4, frame_height // 4),
            description="Demo restricted zone"
        ))
        
        # Example: High-risk zone in center
        cx, cy = frame_width // 2, frame_height // 2
        margin = min(frame_width, frame_height) // 6
        self.add_zone(Zone(
            zone_id="highrisk_demo",
            name="High Risk Zone",
            zone_type=ZoneType.HIGH_RISK,
            bounds=(cx - margin, cy - margin, cx + margin, cy + margin),
            description="Demo high-risk zone"
        ))
        
        logger.info(f"Added {self.zone_count} sample zones")
    
    def clear(self) -> None:
        """Remove all zone definitions."""
        self._zones.clear()
        logger.info("All zones cleared")
    
    def __repr__(self) -> str:
        return f"ZoneManager(zones={self.zone_count})"
