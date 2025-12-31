"""
AegisAI - Smart City Risk Intelligence System
Crowd Analyzer Module

This module analyzes crowd dynamics and spatial density.
Provides frame-level statistics for crowd monitoring.

Features:
- Person and vehicle counts
- Grid-based density estimation
- Hotspot detection (high-density areas)
- Density spike detection
- Crowd event identification

Phase 2: Analysis Layer
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from aegis.analysis.analysis_types import CrowdMetrics, DensityCell
from aegis.tracking.deepsort_tracker import Track

# Configure module logger
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CrowdAnalyzerConfig:
    """
    Configuration for crowd analysis.
    
    Attributes:
        grid_cell_size: Size of density grid cells in pixels
        crowd_density_threshold: Count per cell to consider "crowded"
        density_spike_threshold: Multiplier for detecting density spikes
        person_class_ids: Class IDs that represent persons
        vehicle_class_ids: Class IDs that represent vehicles
    """
    grid_cell_size: int = 100  # pixels
    crowd_density_threshold: int = 5  # objects per cell
    density_spike_threshold: float = 2.0  # multiplier
    person_class_ids: Tuple[int, ...] = (0,)  # COCO: person
    vehicle_class_ids: Tuple[int, ...] = (2, 3, 5, 7)  # car, motorcycle, bus, truck


class CrowdAnalyzer:
    """
    Analyzes crowd density and distribution.
    
    Provides frame-level crowd statistics including counts,
    density maps, and hotspot detection.
    
    Attributes:
        config: Crowd analyzer configuration
        
    Example:
        >>> analyzer = CrowdAnalyzer()
        >>> metrics = analyzer.analyze(tracks, frame_shape)
        >>> print(f"Persons: {metrics.person_count}, Vehicles: {metrics.vehicle_count}")
        >>> if metrics.crowd_detected:
        ...     print("Crowd detected!")
    """
    
    def __init__(self, config: Optional[CrowdAnalyzerConfig] = None):
        """
        Initialize the crowd analyzer.
        
        Args:
            config: Crowd analyzer configuration
        """
        self._config = config or CrowdAnalyzerConfig()
        
        # Store previous metrics for spike detection
        self._previous_metrics: Optional[CrowdMetrics] = None
        
        logger.info(
            f"CrowdAnalyzer initialized with "
            f"grid_cell_size={self._config.grid_cell_size}px"
        )
    
    @property
    def config(self) -> CrowdAnalyzerConfig:
        """Get the analyzer configuration."""
        return self._config
    
    def analyze(
        self,
        tracks: List[Track],
        frame_shape: Tuple[int, int, int]
    ) -> CrowdMetrics:
        """
        Analyze crowd metrics for current frame.
        
        Args:
            tracks: List of active Track objects
            frame_shape: Frame dimensions (height, width, channels)
            
        Returns:
            CrowdMetrics with counts and density information
        """
        height, width = frame_shape[:2]
        
        # Count by class type
        person_count = 0
        vehicle_count = 0
        
        for track in tracks:
            if track.class_id in self._config.person_class_ids:
                person_count += 1
            elif track.class_id in self._config.vehicle_class_ids:
                vehicle_count += 1
        
        total_count = person_count + vehicle_count
        
        # Compute density map
        density_map, hotspots = self._compute_density_map(
            tracks, width, height
        )
        
        # Compute density statistics
        max_density = 0
        total_density = 0
        cell_count = 0
        
        for row in density_map:
            for count in row:
                total_density += count
                if count > max_density:
                    max_density = count
                cell_count += 1
        
        average_density = total_density / cell_count if cell_count > 0 else 0.0
        
        # Compute variance
        if cell_count > 0:
            variance_sum = sum(
                (count - average_density) ** 2
                for row in density_map
                for count in row
            )
            density_variance = variance_sum / cell_count
        else:
            density_variance = 0.0
        
        # Check for crowd conditions
        crowd_detected = max_density >= self._config.crowd_density_threshold
        
        metrics = CrowdMetrics(
            person_count=person_count,
            vehicle_count=vehicle_count,
            total_count=total_count,
            density_map=density_map,
            hotspots=hotspots,
            max_density=max_density,
            average_density=average_density,
            density_variance=density_variance,
            crowd_detected=crowd_detected
        )
        
        # Store for spike detection
        self._previous_metrics = metrics
        
        return metrics
    
    def _compute_density_map(
        self,
        tracks: List[Track],
        width: int,
        height: int
    ) -> Tuple[List[List[int]], List[DensityCell]]:
        """
        Compute grid-based density map.
        
        Args:
            tracks: List of active tracks
            width: Frame width
            height: Frame height
            
        Returns:
            Tuple of (density_map, hotspots)
        """
        cell_size = self._config.grid_cell_size
        
        # Calculate grid dimensions
        cols = max(1, (width + cell_size - 1) // cell_size)
        rows = max(1, (height + cell_size - 1) // cell_size)
        
        # Initialize grid
        density_map = [[0 for _ in range(cols)] for _ in range(rows)]
        
        # Count objects in each cell
        for track in tracks:
            x1, y1, x2, y2 = track.bbox
            center_x = (x1 + x2) / 2
            center_y = (y1 + y2) / 2
            
            # Determine cell
            col = min(int(center_x / cell_size), cols - 1)
            row = min(int(center_y / cell_size), rows - 1)
            
            if 0 <= row < rows and 0 <= col < cols:
                density_map[row][col] += 1
        
        # Find hotspots
        hotspots = []
        threshold = self._config.crowd_density_threshold
        
        for row_idx, row in enumerate(density_map):
            for col_idx, count in enumerate(row):
                if count >= threshold:
                    hotspot = DensityCell(
                        row=row_idx,
                        col=col_idx,
                        count=count,
                        center_x=(col_idx + 0.5) * cell_size,
                        center_y=(row_idx + 0.5) * cell_size
                    )
                    hotspots.append(hotspot)
        
        return density_map, hotspots
    
    def detect_density_spike(
        self,
        current: CrowdMetrics,
        previous: Optional[CrowdMetrics] = None
    ) -> bool:
        """
        Detect sudden increase in density.
        
        Args:
            current: Current frame metrics
            previous: Previous frame metrics (optional)
            
        Returns:
            True if density spike detected
        """
        prev = previous or self._previous_metrics
        
        if prev is None:
            return False
        
        # Check for sudden increase in total count
        if prev.total_count > 0:
            ratio = current.total_count / prev.total_count
            if ratio > self._config.density_spike_threshold:
                logger.info(
                    f"Density spike detected: {prev.total_count} -> "
                    f"{current.total_count} ({ratio:.1f}x)"
                )
                return True
        elif current.total_count > 5:
            # Sudden appearance of multiple objects
            return True
        
        return False
    
    def get_zone_density(
        self,
        tracks: List[Track],
        zone: Tuple[int, int, int, int]
    ) -> int:
        """
        Get object count within a specific zone.
        
        Args:
            tracks: List of active tracks
            zone: Zone bounds (x1, y1, x2, y2)
            
        Returns:
            Count of objects within the zone
        """
        x1_zone, y1_zone, x2_zone, y2_zone = zone
        count = 0
        
        for track in tracks:
            x1, y1, x2, y2 = track.bbox
            center_x = (x1 + x2) / 2
            center_y = (y1 + y2) / 2
            
            if (x1_zone <= center_x <= x2_zone and
                y1_zone <= center_y <= y2_zone):
                count += 1
        
        return count
    
    def reset(self) -> None:
        """Reset analyzer state."""
        self._previous_metrics = None
        logger.info("CrowdAnalyzer reset")
    
    def __repr__(self) -> str:
        return (
            f"CrowdAnalyzer(grid_size={self._config.grid_cell_size}px, "
            f"crowd_threshold={self._config.crowd_density_threshold})"
        )
