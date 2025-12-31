"""
AegisAI - Multi-Camera AI Pipeline

Processes frames from all connected cameras through YOLO detection,
tracking, and risk scoring. Aggregates results for API access.

Features:
- Parallel processing of multiple camera streams
- Per-camera YOLO detection and tracking
- Centralized detection storage
- Event callbacks for real-time notifications

Copyright 2024 AegisAI Project
"""

import logging
import threading
import time
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime
from collections import deque
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from aegis.video.camera_manager import CameraManager, CameraHealth
from aegis.utils.credentials import get_secure_logger

logger = get_secure_logger(__name__)


@dataclass
class DetectionResult:
    """Single detection from AI pipeline."""
    camera_id: str
    track_id: Optional[int]
    class_name: str
    class_id: int
    confidence: float
    bbox: tuple  # (x1, y1, x2, y2)
    risk_level: str
    risk_score: float
    timestamp: datetime
    frame_id: int
    
    def to_dict(self) -> dict:
        return {
            "camera_id": self.camera_id,
            "track_id": self.track_id,
            "class_name": self.class_name,
            "class_id": self.class_id,
            "confidence": round(self.confidence, 3),
            "bbox": list(self.bbox),
            "risk_level": self.risk_level,
            "risk_score": round(self.risk_score, 3),
            "timestamp": self.timestamp.isoformat(),
            "frame_id": self.frame_id,
        }


@dataclass
class CameraDetectionStats:
    """Detection statistics per camera."""
    camera_id: str
    total_detections: int = 0
    persons_detected: int = 0
    vehicles_detected: int = 0
    max_risk_level: str = "LOW"
    max_risk_score: float = 0.0
    last_detection_time: Optional[datetime] = None
    fps: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            "camera_id": self.camera_id,
            "total_detections": self.total_detections,
            "persons_detected": self.persons_detected,
            "vehicles_detected": self.vehicles_detected,
            "max_risk_level": self.max_risk_level,
            "max_risk_score": round(self.max_risk_score, 3),
            "last_detection_time": self.last_detection_time.isoformat() if self.last_detection_time else None,
            "fps": round(self.fps, 2),
        }


class AICameraPipeline:
    """
    Multi-camera AI processing pipeline.
    
    Processes frames from CameraManager through YOLO detection,
    tracking, and risk scoring. Stores results for API access.
    
    Example:
        >>> manager = CameraManager()
        >>> manager.add_camera("cam1", "rtsp://...")
        >>> 
        >>> pipeline = AICameraPipeline(manager)
        >>> pipeline.start()
        >>> 
        >>> # Get recent detections
        >>> detections = pipeline.get_recent_detections()
        >>> 
        >>> pipeline.stop()
    """
    
    def __init__(
        self,
        camera_manager: CameraManager,
        detection_buffer_size: int = 1000,
        process_interval_ms: int = 100,  # Process every 100ms
        on_detection: Optional[Callable[[DetectionResult], None]] = None,
        on_high_risk: Optional[Callable[[DetectionResult], None]] = None,
    ):
        """
        Initialize AI pipeline.
        
        Args:
            camera_manager: CameraManager with connected cameras
            detection_buffer_size: Max detections to store
            process_interval_ms: Interval between frame processing
            on_detection: Callback for each detection
            on_high_risk: Callback for high-risk detections
        """
        self._camera_manager = camera_manager
        self._buffer_size = detection_buffer_size
        self._process_interval = process_interval_ms / 1000.0
        self._on_detection = on_detection
        self._on_high_risk = on_high_risk
        
        # State
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._executor = ThreadPoolExecutor(max_workers=16)
        
        # Detection storage
        self._detections: deque = deque(maxlen=detection_buffer_size)
        self._detection_lock = threading.Lock()
        
        # Per-camera stats
        self._camera_stats: Dict[str, CameraDetectionStats] = {}
        self._stats_lock = threading.Lock()
        
        # Frame counters
        self._frame_counters: Dict[str, int] = {}
        
        # AI components (lazy loaded)
        self._detector = None
        self._trackers: Dict[str, Any] = {}
        self._risk_scorer = None
        
        logger.info("AICameraPipeline initialized")
    
    def _get_detector(self):
        """Lazy load YOLO detector."""
        if self._detector is None:
            try:
                from aegis.detection.yolo_detector import YOLODetector
                self._detector = YOLODetector()
                self._detector.warmup()
                logger.info("YOLO detector loaded and warmed up")
            except Exception as e:
                logger.error(f"Failed to load detector: {e}")
        return self._detector
    
    def _get_tracker(self, camera_id: str):
        """Get or create tracker for camera."""
        if camera_id not in self._trackers:
            try:
                from aegis.tracking.deepsort_tracker import DeepSORTTracker
                self._trackers[camera_id] = DeepSORTTracker()
                logger.info(f"Created tracker for camera: {camera_id}")
            except Exception as e:
                logger.error(f"Failed to create tracker: {e}")
                return None
        return self._trackers[camera_id]
    
    def _get_risk_scorer(self):
        """Lazy load risk scorer."""
        if self._risk_scorer is None:
            try:
                from aegis.risk.risk_scorer import RiskScorer
                self._risk_scorer = RiskScorer()
                logger.info("Risk scorer loaded")
            except Exception as e:
                logger.error(f"Failed to load risk scorer: {e}")
        return self._risk_scorer
    
    def _process_camera_frame(self, camera_id: str, frame: np.ndarray):
        """Process a single frame from a camera."""
        detector = self._get_detector()
        if detector is None:
            return
        
        # Update frame counter
        self._frame_counters[camera_id] = self._frame_counters.get(camera_id, 0) + 1
        frame_id = self._frame_counters[camera_id]
        
        try:
            # Run detection
            detections = detector.detect(frame)
            
            # Run tracking
            tracker = self._get_tracker(camera_id)
            if tracker and detections:
                tracks = tracker.update(detections, frame)
            else:
                tracks = detections
            
            # Get risk scorer
            risk_scorer = self._get_risk_scorer()
            
            # Process each detection
            for det in tracks:
                # Extract detection info
                if hasattr(det, 'bbox'):
                    bbox = det.bbox
                    class_name = det.class_name
                    class_id = det.class_id
                    confidence = det.confidence
                    track_id = getattr(det, 'track_id', None)
                else:
                    bbox = det.get('bbox', det.get('box', (0, 0, 0, 0)))
                    class_name = det.get('class_name', det.get('label', 'unknown'))
                    class_id = det.get('class_id', 0)
                    confidence = det.get('confidence', det.get('score', 0.0))
                    track_id = det.get('track_id')
                
                # Calculate risk
                risk_level = "LOW"
                risk_score = 0.1
                if risk_scorer:
                    try:
                        risk_result = risk_scorer.calculate_risk(det, frame)
                        risk_level = risk_result.get('level', 'LOW')
                        risk_score = risk_result.get('score', 0.1)
                    except:
                        pass
                
                # Create detection result
                result = DetectionResult(
                    camera_id=camera_id,
                    track_id=track_id,
                    class_name=class_name,
                    class_id=class_id,
                    confidence=confidence,
                    bbox=tuple(bbox) if not isinstance(bbox, tuple) else bbox,
                    risk_level=risk_level,
                    risk_score=risk_score,
                    timestamp=datetime.utcnow(),
                    frame_id=frame_id,
                )
                
                # Store detection
                with self._detection_lock:
                    self._detections.append(result)
                
                # Update stats
                self._update_stats(result)
                
                # Callbacks
                if self._on_detection:
                    try:
                        self._on_detection(result)
                    except Exception as e:
                        logger.error(f"Detection callback error: {e}")
                
                if risk_level in ('HIGH', 'CRITICAL') and self._on_high_risk:
                    try:
                        self._on_high_risk(result)
                    except Exception as e:
                        logger.error(f"High risk callback error: {e}")
        
        except Exception as e:
            logger.error(f"Frame processing error for {camera_id}: {e}")
    
    def _update_stats(self, detection: DetectionResult):
        """Update per-camera statistics."""
        with self._stats_lock:
            if detection.camera_id not in self._camera_stats:
                self._camera_stats[detection.camera_id] = CameraDetectionStats(
                    camera_id=detection.camera_id
                )
            
            stats = self._camera_stats[detection.camera_id]
            stats.total_detections += 1
            stats.last_detection_time = detection.timestamp
            
            if detection.class_name.lower() == 'person':
                stats.persons_detected += 1
            elif detection.class_name.lower() in ('car', 'truck', 'bus', 'motorcycle'):
                stats.vehicles_detected += 1
            
            if detection.risk_score > stats.max_risk_score:
                stats.max_risk_score = detection.risk_score
                stats.max_risk_level = detection.risk_level
    
    def _processing_loop(self):
        """Main processing loop."""
        logger.info("AI pipeline processing started")
        
        last_process_time = 0
        
        while self._running:
            current_time = time.time()
            
            # Throttle processing
            if current_time - last_process_time < self._process_interval:
                time.sleep(0.01)
                continue
            
            last_process_time = current_time
            
            # Get frames from all cameras
            cameras = self._camera_manager._cameras
            
            for camera_id, camera in list(cameras.items()):
                if camera.health != CameraHealth.UP:
                    continue
                
                frame = camera.get_frame(timeout=0.01)
                if frame is not None:
                    # Process in thread pool
                    self._executor.submit(
                        self._process_camera_frame, camera_id, frame
                    )
        
        logger.info("AI pipeline processing stopped")
    
    def start(self):
        """Start the AI pipeline."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._processing_loop, daemon=True)
        self._thread.start()
        
        logger.info("AICameraPipeline started")
    
    def stop(self):
        """Stop the AI pipeline."""
        if not self._running:
            return
        
        self._running = False
        
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        
        self._executor.shutdown(wait=False, cancel_futures=True)
        
        logger.info("AICameraPipeline stopped")
    
    def get_recent_detections(
        self,
        limit: int = 100,
        camera_id: Optional[str] = None,
        class_name: Optional[str] = None,
        min_risk_score: Optional[float] = None,
    ) -> List[dict]:
        """
        Get recent detections with optional filters.
        
        Args:
            limit: Maximum detections to return
            camera_id: Filter by camera
            class_name: Filter by class (person, car, etc.)
            min_risk_score: Filter by minimum risk score
            
        Returns:
            List of detection dictionaries
        """
        with self._detection_lock:
            results = list(self._detections)
        
        # Apply filters
        if camera_id:
            results = [d for d in results if d.camera_id == camera_id]
        if class_name:
            results = [d for d in results if d.class_name.lower() == class_name.lower()]
        if min_risk_score:
            results = [d for d in results if d.risk_score >= min_risk_score]
        
        # Return most recent
        return [d.to_dict() for d in results[-limit:]]
    
    def get_camera_stats(self, camera_id: Optional[str] = None) -> Dict[str, dict]:
        """Get detection statistics per camera."""
        with self._stats_lock:
            if camera_id:
                if camera_id in self._camera_stats:
                    return {camera_id: self._camera_stats[camera_id].to_dict()}
                return {}
            return {cid: stats.to_dict() for cid, stats in self._camera_stats.items()}
    
    def get_aggregated_stats(self) -> dict:
        """Get aggregated statistics across all cameras."""
        with self._stats_lock:
            total_detections = sum(s.total_detections for s in self._camera_stats.values())
            total_persons = sum(s.persons_detected for s in self._camera_stats.values())
            total_vehicles = sum(s.vehicles_detected for s in self._camera_stats.values())
            
            max_risk_level = "LOW"
            max_risk_score = 0.0
            for stats in self._camera_stats.values():
                if stats.max_risk_score > max_risk_score:
                    max_risk_score = stats.max_risk_score
                    max_risk_level = stats.max_risk_level
            
            return {
                "cameras_processing": len(self._camera_stats),
                "total_detections": total_detections,
                "total_persons": total_persons,
                "total_vehicles": total_vehicles,
                "max_risk_level": max_risk_level,
                "max_risk_score": round(max_risk_score, 3),
                "buffer_size": len(self._detections),
                "running": self._running,
            }
    
    def clear_stats(self):
        """Clear all statistics and detections."""
        with self._detection_lock:
            self._detections.clear()
        with self._stats_lock:
            self._camera_stats.clear()
        self._frame_counters.clear()
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
