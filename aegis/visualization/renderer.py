"""
AegisAI - Smart City Risk Intelligence System
Visualization Renderer Module

This module provides production-grade visualization for detection
and tracking results. Renders bounding boxes, labels, and ID annotations.

Features:
- Color-coded bounding boxes by class
- Track ID labels with readable formatting
- Configurable appearance (thickness, font size)
- Professional-grade annotations
"""

import logging
from typing import List, Optional, Tuple

import cv2
import numpy as np

from config import VisualizationConfig, DetectionConfig, AegisConfig
from aegis.detection.yolo_detector import Detection
from aegis.tracking.deepsort_tracker import Track

# Configure module logger
logger = logging.getLogger(__name__)


class Renderer:
    """
    Production-grade visualization renderer.
    
    Renders detection and tracking results onto video frames
    with professional-quality annotations.
    
    Attributes:
        config: Visualization configuration parameters
        
    Example:
        >>> renderer = Renderer(config)
        >>> annotated = renderer.draw_tracks(frame, tracks)
        >>> annotated = renderer.draw_detections(frame, detections)
    """
    
    def __init__(
        self,
        config: Optional[AegisConfig] = None,
        visualization_config: Optional[VisualizationConfig] = None,
        detection_config: Optional[DetectionConfig] = None
    ):
        """
        Initialize the renderer.
        
        Args:
            config: Full AegisConfig instance (preferred)
            visualization_config: VisualizationConfig instance
            detection_config: DetectionConfig for class names
        """
        if config is not None:
            self._config = config.visualization
            self._detection_config = config.detection
        else:
            self._config = visualization_config or VisualizationConfig()
            self._detection_config = detection_config or DetectionConfig()
        
        # Pre-compute colors for efficiency
        self._class_colors = dict(self._config.CLASS_COLORS)
        self._default_color = self._config.DEFAULT_COLOR
        self._class_names = dict(self._detection_config.CLASS_NAMES)
        
        logger.info("Renderer initialized")
    
    def get_color(self, class_id: int) -> Tuple[int, int, int]:
        """
        Get the color for a specific class.
        
        Args:
            class_id: COCO class identifier
            
        Returns:
            BGR color tuple
        """
        return self._class_colors.get(class_id, self._default_color)
    
    def draw_tracks(
        self,
        frame: np.ndarray,
        tracks: List[Track],
        copy: bool = True
    ) -> np.ndarray:
        """
        Draw tracking results on a frame.
        
        Args:
            frame: Input video frame (BGR format)
            tracks: List of Track objects to visualize
            copy: Whether to copy the frame (preserves original)
            
        Returns:
            Annotated frame with bounding boxes and IDs
        """
        if copy:
            frame = frame.copy()
        
        for track in tracks:
            x1, y1, x2, y2 = track.bbox
            color = self.get_color(track.class_id)
            
            # Draw bounding box
            cv2.rectangle(
                frame,
                (x1, y1),
                (x2, y2),
                color,
                self._config.bbox_thickness
            )
            
            # Build label text
            label_parts = []
            
            if self._config.show_track_id:
                label_parts.append(f"ID:{track.track_id}")
            
            if self._config.show_class_name:
                label_parts.append(track.class_name)
            
            if self._config.show_confidence and track.confidence > 0:
                label_parts.append(f"{track.confidence:.2f}")
            
            label = " | ".join(label_parts)
            
            # Draw label background and text
            self._draw_label(frame, label, (x1, y1), color)
        
        return frame
    
    def draw_detections(
        self,
        frame: np.ndarray,
        detections: List[Detection],
        copy: bool = True
    ) -> np.ndarray:
        """
        Draw detection results on a frame (without tracking).
        
        Args:
            frame: Input video frame (BGR format)
            detections: List of Detection objects to visualize
            copy: Whether to copy the frame (preserves original)
            
        Returns:
            Annotated frame with bounding boxes
        """
        if copy:
            frame = frame.copy()
        
        for det in detections:
            x1, y1, x2, y2 = det.bbox
            color = self.get_color(det.class_id)
            
            # Draw bounding box
            cv2.rectangle(
                frame,
                (x1, y1),
                (x2, y2),
                color,
                self._config.bbox_thickness
            )
            
            # Build label text
            label_parts = []
            
            if self._config.show_class_name:
                label_parts.append(det.class_name)
            
            if self._config.show_confidence:
                label_parts.append(f"{det.confidence:.2f}")
            
            label = " | ".join(label_parts)
            
            # Draw label
            self._draw_label(frame, label, (x1, y1), color)
        
        return frame
    
    def _draw_label(
        self,
        frame: np.ndarray,
        label: str,
        position: Tuple[int, int],
        color: Tuple[int, int, int]
    ) -> None:
        """
        Draw a label with background at the specified position.
        
        Args:
            frame: Frame to draw on (modified in place)
            label: Text to display
            position: Top-left corner (x, y)
            color: Background color
        """
        x, y = position
        padding = self._config.label_padding
        
        # Get text size
        (text_width, text_height), baseline = cv2.getTextSize(
            label,
            cv2.FONT_HERSHEY_SIMPLEX,
            self._config.font_scale,
            self._config.font_thickness
        )
        
        # Calculate background rectangle
        bg_x1 = x
        bg_y1 = y - text_height - 2 * padding
        bg_x2 = x + text_width + 2 * padding
        bg_y2 = y
        
        # Ensure label stays within frame bounds
        if bg_y1 < 0:
            # Draw below the box instead
            bg_y1 = y
            bg_y2 = y + text_height + 2 * padding
            text_y = bg_y2 - padding
        else:
            text_y = y - padding
        
        # Draw background rectangle
        cv2.rectangle(
            frame,
            (bg_x1, bg_y1),
            (bg_x2, bg_y2),
            color,
            -1  # Filled
        )
        
        # Calculate text color (black or white based on background brightness)
        brightness = sum(color) / 3
        text_color = (0, 0, 0) if brightness > 127 else (255, 255, 255)
        
        # Draw text
        cv2.putText(
            frame,
            label,
            (x + padding, text_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            self._config.font_scale,
            text_color,
            self._config.font_thickness,
            cv2.LINE_AA
        )
    
    def draw_info_overlay(
        self,
        frame: np.ndarray,
        info: dict,
        copy: bool = True
    ) -> np.ndarray:
        """
        Draw an information overlay on the frame.
        
        Args:
            frame: Input video frame
            info: Dictionary of info to display (e.g., FPS, frame count)
            copy: Whether to copy the frame
            
        Returns:
            Frame with info overlay
        """
        if copy:
            frame = frame.copy()
        
        # Build info text
        info_lines = [f"{k}: {v}" for k, v in info.items()]
        
        y_offset = 30
        for line in info_lines:
            # Draw shadow
            cv2.putText(
                frame,
                line,
                (12, y_offset + 2),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 0, 0),
                2,
                cv2.LINE_AA
            )
            
            # Draw text
            cv2.putText(
                frame,
                line,
                (10, y_offset),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
                cv2.LINE_AA
            )
            
            y_offset += 30
        
        return frame
    
    def draw_track_trail(
        self,
        frame: np.ndarray,
        track_history: dict,
        max_trail_length: int = 30,
        copy: bool = True
    ) -> np.ndarray:
        """
        Draw motion trails for tracked objects.
        
        Args:
            frame: Input video frame
            track_history: Dict mapping track_id to list of center points
            max_trail_length: Maximum trail length to display
            copy: Whether to copy the frame
            
        Returns:
            Frame with motion trails
        """
        if copy:
            frame = frame.copy()
        
        for track_id, points in track_history.items():
            if len(points) < 2:
                continue
            
            # Limit trail length
            if len(points) > max_trail_length:
                points = points[-max_trail_length:]
            
            # Draw trail with fading effect
            for i in range(1, len(points)):
                alpha = i / len(points)
                thickness = max(1, int(3 * alpha))
                
                pt1 = tuple(map(int, points[i - 1]))
                pt2 = tuple(map(int, points[i]))
                
                # Color fades from dark to bright
                color_intensity = int(255 * alpha)
                color = (0, color_intensity, color_intensity)
                
                cv2.line(frame, pt1, pt2, color, thickness, cv2.LINE_AA)
        
        return frame
    
    def __repr__(self) -> str:
        return (
            f"Renderer(font_scale={self._config.font_scale}, "
            f"bbox_thickness={self._config.bbox_thickness})"
        )
