"""
AegisAI - Smart City Risk Intelligence System
DeepSORT Multi-Object Tracker Module

This module provides production-grade multi-object tracking using DeepSORT.
Maintains stable unique IDs across video frames for detected objects.

Features:
- Robust ID assignment with appearance features
- Configurable track lifecycle management
- Seamless integration with detection module
- Handles occlusion and temporary disappearance
"""

import logging
from typing import List, Tuple, Optional, NamedTuple

import numpy as np
from deep_sort_realtime.deepsort_tracker import DeepSort

from config import TrackingConfig, AegisConfig
from aegis.detection.yolo_detector import Detection

# Configure module logger
logger = logging.getLogger(__name__)


class Track(NamedTuple):
    """
    Standardized tracking result container.
    
    Attributes:
        track_id: Unique identifier for this track
        bbox: Bounding box coordinates (x1, y1, x2, y2) in pixels
        class_id: COCO class identifier from original detection
        class_name: Human-readable class name
        confidence: Original detection confidence
        is_confirmed: Whether track has enough detections to be confirmed
    """
    track_id: int
    bbox: Tuple[int, int, int, int]
    class_id: int
    class_name: str
    confidence: float
    is_confirmed: bool


class DeepSORTTracker:
    """
    Production-grade DeepSORT multi-object tracker.
    
    Provides stable ID assignment across frames using appearance
    features and motion prediction. Designed for real-time
    tracking in urban surveillance scenarios.
    
    Attributes:
        config: Tracking configuration parameters
        tracker: Internal DeepSORT tracker instance
        
    Example:
        >>> tracker = DeepSORTTracker(config)
        >>> detections = detector.detect(frame)
        >>> tracks = tracker.update(detections, frame)
        >>> for track in tracks:
        ...     print(f"ID {track.track_id}: {track.class_name}")
    """
    
    def __init__(
        self,
        config: Optional[AegisConfig] = None,
        tracking_config: Optional[TrackingConfig] = None
    ):
        """
        Initialize the DeepSORT tracker.
        
        Args:
            config: Full AegisConfig instance (preferred)
            tracking_config: TrackingConfig instance (alternative)
        """
        if config is not None:
            self._config = config.tracking
        elif tracking_config is not None:
            self._config = tracking_config
        else:
            self._config = TrackingConfig()
        
        # Initialize DeepSORT tracker
        self._tracker = DeepSort(
            max_age=self._config.max_age,
            n_init=self._config.n_init,
            max_iou_distance=self._config.max_iou_distance,
            max_cosine_distance=self._config.max_cosine_distance,
            nn_budget=self._config.nn_budget,
            embedder=self._config.embedder,
            embedder_gpu=self._config.embedder_gpu
        )
        
        # Track metadata storage (class info per track_id)
        self._track_metadata: dict = {}
        
        logger.info(
            f"DeepSORTTracker initialized with max_age={self._config.max_age}, "
            f"n_init={self._config.n_init}, embedder={self._config.embedder}"
        )
    
    def update(
        self,
        detections: List[Detection],
        frame: np.ndarray
    ) -> List[Track]:
        """
        Update tracker with new detections and return active tracks.
        
        This is the primary method for tracking. Call it once per frame
        with the detection results from the detector module.
        
        Args:
            detections: List of Detection objects from current frame
            frame: Current video frame (required for appearance features)
            
        Returns:
            List of Track objects for all confirmed tracks
        """
        if len(detections) == 0:
            # Update tracker with empty detections to age existing tracks
            tracks = self._tracker.update_tracks([], frame=frame)
            return self._format_tracks(tracks)
        
        # Convert detections to DeepSORT format
        # Format: [[x1, y1, width, height, confidence], ...]
        deepsort_detections = []
        detection_metadata = []
        
        for det in detections:
            x1, y1, x2, y2 = det.bbox
            width = x2 - x1
            height = y2 - y1
            
            # DeepSORT expects [left, top, width, height]
            deepsort_detections.append(
                ([x1, y1, width, height], det.confidence, det.class_name)
            )
            
            # Store metadata for track association
            detection_metadata.append({
                'class_id': det.class_id,
                'class_name': det.class_name,
                'confidence': det.confidence
            })
        
        # Update tracker
        tracks = self._tracker.update_tracks(
            deepsort_detections,
            frame=frame
        )
        
        # Update metadata for new tracks
        for track in tracks:
            if track.is_confirmed() and track.track_id not in self._track_metadata:
                # Get class info from the detection that created this track
                if track.det_class is not None:
                    # Find matching detection
                    for det in detections:
                        if det.class_name == track.det_class:
                            self._track_metadata[track.track_id] = {
                                'class_id': det.class_id,
                                'class_name': det.class_name
                            }
                            break
                    else:
                        # Fallback if no match found
                        self._track_metadata[track.track_id] = {
                            'class_id': 0,
                            'class_name': track.det_class or 'Unknown'
                        }
        
        return self._format_tracks(tracks)
    
    def _format_tracks(self, raw_tracks) -> List[Track]:
        """
        Convert DeepSORT tracks to standardized Track format.
        
        Args:
            raw_tracks: List of DeepSORT track objects
            
        Returns:
            List of Track namedtuples
        """
        formatted_tracks = []
        
        for track in raw_tracks:
            # Skip unconfirmed tracks
            if not track.is_confirmed():
                continue
            
            # Skip deleted tracks
            if track.is_deleted():
                continue
            
            # Get bounding box (convert from ltwh to xyxy)
            ltwh = track.to_ltwh()
            x1 = int(ltwh[0])
            y1 = int(ltwh[1])
            x2 = int(ltwh[0] + ltwh[2])
            y2 = int(ltwh[1] + ltwh[3])
            
            # Get metadata
            metadata = self._track_metadata.get(track.track_id, {})
            class_id = metadata.get('class_id', 0)
            class_name = metadata.get('class_name', track.det_class or 'Unknown')
            
            # Get confidence (use detection confidence if available)
            confidence = track.det_conf if track.det_conf is not None else 0.0
            
            formatted_track = Track(
                track_id=track.track_id,
                bbox=(x1, y1, x2, y2),
                class_id=class_id,
                class_name=class_name,
                confidence=confidence,
                is_confirmed=True
            )
            formatted_tracks.append(formatted_track)
        
        logger.debug(f"Active tracks: {len(formatted_tracks)}")
        return formatted_tracks
    
    def get_track_count(self) -> int:
        """
        Get the current number of active confirmed tracks.
        
        Returns:
            Number of active tracks
        """
        return len([
            t for t in self._tracker.tracker.tracks
            if t.is_confirmed() and not t.is_deleted()
        ])
    
    def get_total_tracks_created(self) -> int:
        """
        Get the total number of unique tracks created since initialization.
        
        Useful for analytics and understanding traffic volume.
        
        Returns:
            Total unique track count
        """
        return self._tracker.tracker._next_id - 1
    
    def reset(self) -> None:
        """
        Reset the tracker state.
        
        Clears all active tracks and metadata. Use when switching
        to a new video source or after significant scene changes.
        """
        self._tracker = DeepSort(
            max_age=self._config.max_age,
            n_init=self._config.n_init,
            max_iou_distance=self._config.max_iou_distance,
            max_cosine_distance=self._config.max_cosine_distance,
            nn_budget=self._config.nn_budget,
            embedder=self._config.embedder,
            embedder_gpu=self._config.embedder_gpu
        )
        self._track_metadata.clear()
        logger.info("Tracker reset complete")
    
    def __repr__(self) -> str:
        return (
            f"DeepSORTTracker(max_age={self._config.max_age}, "
            f"n_init={self._config.n_init}, "
            f"active_tracks={self.get_track_count()})"
        )
