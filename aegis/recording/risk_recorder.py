"""
AegisAI - Risk-Based Video Recorder

Automatic recording when risk thresholds are exceeded.
Includes pre-event circular buffer for context.

Copyright 2024 AegisAI Project
"""

import cv2
import numpy as np
import threading
import logging
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List

from aegis.recording.models import RecordingEvent, RecordingMetadata

logger = logging.getLogger(__name__)


@dataclass
class RecorderConfig:
    """Configuration for risk recorder."""
    # Risk thresholds
    start_threshold: float = 0.7  # Start recording when risk > this
    stop_threshold: float = 0.4   # Stop when risk < this for cooldown
    stop_cooldown_seconds: float = 10.0  # Time below threshold before stopping
    
    # Buffer settings
    pre_buffer_seconds: float = 5.0  # Seconds of pre-event frames to keep
    target_fps: int = 30  # Target FPS for buffer calculation
    
    # Output settings
    output_base_path: str = "data/recordings"
    output_codec: str = "mp4v"  # or 'avc1' for H.264
    
    # Performance
    max_concurrent_writes: int = 2
    
    @property
    def buffer_size(self) -> int:
        """Calculate buffer size in frames."""
        return int(self.pre_buffer_seconds * self.target_fps)


class RiskRecorder:
    """
    Risk-triggered video recorder with pre-event buffering.
    
    Features:
    - Circular buffer maintains last N seconds of frames
    - Starts recording when risk exceeds threshold
    - Continues until risk drops below threshold for cooldown period
    - Non-blocking recording via thread pool
    - Graceful failure handling
    
    Usage:
        recorder = RiskRecorder(camera_id="cam_01")
        recorder.start()
        
        # In processing loop:
        recorder.process_frame(frame, risk_score, detections)
        
        # On shutdown:
        recorder.stop()
    """
    
    def __init__(
        self,
        camera_id: str,
        config: Optional[RecorderConfig] = None,
        metadata_storage: Optional[RecordingMetadata] = None,
        on_recording_start: Optional[Callable[[RecordingEvent], None]] = None,
        on_recording_end: Optional[Callable[[RecordingEvent], None]] = None,
    ):
        """
        Initialize the recorder.
        
        Args:
            camera_id: Unique camera identifier
            config: Recorder configuration
            metadata_storage: Shared metadata storage
            on_recording_start: Callback when recording starts
            on_recording_end: Callback when recording ends
        """
        self._camera_id = camera_id
        self._config = config or RecorderConfig()
        self._metadata = metadata_storage or RecordingMetadata()
        self._on_start = on_recording_start
        self._on_end = on_recording_end
        
        # Frame buffer (circular)
        self._buffer: deque = deque(maxlen=self._config.buffer_size)
        self._buffer_lock = threading.Lock()
        
        # Recording state
        self._is_recording = False
        self._current_event: Optional[RecordingEvent] = None
        self._recording_frames: List[np.ndarray] = []
        self._recording_lock = threading.Lock()
        
        # Stop cooldown tracking
        self._low_risk_start: Optional[float] = None
        
        # Thread pool for non-blocking writes
        self._executor = ThreadPoolExecutor(
            max_workers=self._config.max_concurrent_writes,
            thread_name_prefix="recorder"
        )
        
        # Frame dimensions (detected from first frame)
        self._frame_width = 0
        self._frame_height = 0
        
        self._running = False
        
        logger.info(f"RiskRecorder initialized for {camera_id}")
    
    @property
    def camera_id(self) -> str:
        return self._camera_id
    
    @property
    def is_recording(self) -> bool:
        return self._is_recording
    
    def start(self) -> None:
        """Start the recorder."""
        self._running = True
        logger.info(f"RiskRecorder started for {self._camera_id}")
    
    def stop(self) -> None:
        """Stop the recorder and finalize any active recording."""
        self._running = False
        
        # Finalize current recording if active
        if self._is_recording and self._current_event:
            self._finalize_recording()
        
        # Shutdown executor
        self._executor.shutdown(wait=True)
        logger.info(f"RiskRecorder stopped for {self._camera_id}")
    
    def process_frame(
        self,
        frame: np.ndarray,
        risk_score: float,
        detections: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        """
        Process a frame with its risk score.
        
        Args:
            frame: Video frame (numpy array, BGR)
            risk_score: Current risk score (0-1)
            detections: List of detection dictionaries
        """
        if not self._running:
            return
        
        try:
            # Update frame dimensions
            if self._frame_height == 0:
                self._frame_height, self._frame_width = frame.shape[:2]
            
            # Add to circular buffer
            with self._buffer_lock:
                self._buffer.append(frame.copy())
            
            # Handle recording logic
            self._handle_risk_state(frame, risk_score, detections or [])
            
        except Exception as e:
            logger.error(f"Error processing frame: {e}")
    
    def _handle_risk_state(
        self,
        frame: np.ndarray,
        risk_score: float,
        detections: List[Dict[str, Any]]
    ) -> None:
        """Handle recording state based on risk score."""
        
        if not self._is_recording:
            # Check if should start recording
            if risk_score > self._config.start_threshold:
                self._start_recording(risk_score)
        
        if self._is_recording:
            # Add frame to recording
            with self._recording_lock:
                self._recording_frames.append(frame.copy())
                
                # Update max risk score
                if self._current_event:
                    self._current_event.max_risk_score = max(
                        self._current_event.max_risk_score,
                        risk_score
                    )
                    
                    # Add detected object types
                    for det in detections:
                        class_name = det.get('class_name', det.get('label', ''))
                        if class_name and class_name not in self._current_event.detected_object_types:
                            self._current_event.detected_object_types.append(class_name)
            
            # Check if should stop recording
            if risk_score < self._config.stop_threshold:
                if self._low_risk_start is None:
                    self._low_risk_start = time.time()
                elif time.time() - self._low_risk_start >= self._config.stop_cooldown_seconds:
                    self._finalize_recording()
            else:
                # Risk went back up, reset cooldown
                self._low_risk_start = None
    
    def _start_recording(self, trigger_score: float) -> None:
        """Start a new recording."""
        try:
            with self._recording_lock:
                # Create event
                self._current_event = RecordingEvent.create(
                    camera_id=self._camera_id,
                    trigger_score=trigger_score
                )
                
                # Copy pre-buffer frames
                with self._buffer_lock:
                    self._recording_frames = list(self._buffer)
                
                self._is_recording = True
                self._low_risk_start = None
                
                logger.info(
                    f"Recording started for {self._camera_id}: "
                    f"{self._current_event.event_id} (trigger: {trigger_score:.2f})"
                )
                
                # Callback
                if self._on_start and self._current_event:
                    try:
                        self._on_start(self._current_event)
                    except Exception as e:
                        logger.error(f"on_recording_start callback error: {e}")
                        
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            self._is_recording = False
    
    def _finalize_recording(self) -> None:
        """Finalize and save the current recording."""
        if not self._current_event:
            self._is_recording = False
            return
        
        try:
            with self._recording_lock:
                event = self._current_event
                frames = self._recording_frames.copy()
                
                self._is_recording = False
                self._current_event = None
                self._recording_frames = []
                self._low_risk_start = None
            
            # Write in background thread
            self._executor.submit(self._write_video, event, frames)
            
        except Exception as e:
            logger.error(f"Failed to finalize recording: {e}")
            self._is_recording = False
    
    def _write_video(self, event: RecordingEvent, frames: List[np.ndarray]) -> None:
        """Write video file (runs in thread pool)."""
        if not frames:
            logger.warning(f"No frames to write for {event.event_id}")
            return
        
        try:
            # Build output path
            date_str = event.start_time.strftime("%Y-%m-%d")
            output_dir = Path(self._config.output_base_path) / self._camera_id / date_str
            output_dir.mkdir(parents=True, exist_ok=True)
            
            output_path = output_dir / f"{event.event_id}.mp4"
            
            # Get frame dimensions
            height, width = frames[0].shape[:2]
            
            # Create video writer
            fourcc = cv2.VideoWriter_fourcc(*self._config.output_codec)
            writer = cv2.VideoWriter(
                str(output_path),
                fourcc,
                self._config.target_fps,
                (width, height)
            )
            
            if not writer.isOpened():
                logger.error(f"Failed to open video writer for {output_path}")
                return
            
            # Write frames
            for frame in frames:
                writer.write(frame)
            
            writer.release()
            
            # Finalize event metadata
            event.finalize(str(output_path))
            
            # Save metadata atomically
            self._metadata.add(event)
            
            logger.info(
                f"Recording saved: {output_path} "
                f"({len(frames)} frames, {event.duration_seconds:.1f}s, "
                f"max_risk: {event.max_risk_score:.2f})"
            )
            
            # Callback
            if self._on_end:
                try:
                    self._on_end(event)
                except Exception as e:
                    logger.error(f"on_recording_end callback error: {e}")
                    
        except Exception as e:
            logger.error(f"Failed to write video {event.event_id}: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get recorder statistics."""
        return {
            "camera_id": self._camera_id,
            "is_recording": self._is_recording,
            "buffer_size": len(self._buffer),
            "buffer_capacity": self._config.buffer_size,
            "current_event_id": self._current_event.event_id if self._current_event else None,
            "frames_in_recording": len(self._recording_frames),
        }


class MultiCameraRecorder:
    """
    Manager for multiple camera recorders.
    
    Provides unified interface for risk-based recording
    across all cameras.
    """
    
    def __init__(
        self,
        config: Optional[RecorderConfig] = None,
        metadata_storage: Optional[RecordingMetadata] = None
    ):
        """Initialize multi-camera recorder."""
        self._config = config or RecorderConfig()
        self._metadata = metadata_storage or RecordingMetadata()
        self._recorders: Dict[str, RiskRecorder] = {}
        self._lock = threading.Lock()
    
    def get_recorder(self, camera_id: str) -> RiskRecorder:
        """Get or create recorder for camera."""
        with self._lock:
            if camera_id not in self._recorders:
                self._recorders[camera_id] = RiskRecorder(
                    camera_id=camera_id,
                    config=self._config,
                    metadata_storage=self._metadata
                )
                self._recorders[camera_id].start()
            return self._recorders[camera_id]
    
    def process_frame(
        self,
        camera_id: str,
        frame: np.ndarray,
        risk_score: float,
        detections: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        """Process frame for specific camera."""
        recorder = self.get_recorder(camera_id)
        recorder.process_frame(frame, risk_score, detections)
    
    def stop_all(self) -> None:
        """Stop all recorders."""
        with self._lock:
            for recorder in self._recorders.values():
                recorder.stop()
            self._recorders.clear()
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get stats for all recorders."""
        with self._lock:
            return {cid: r.get_stats() for cid, r in self._recorders.items()}
