"""
AegisAI - Multi-Camera Manager

Orchestrates multiple RTSP cameras with independent processing pipelines.
Provides centralized health monitoring and event aggregation.

Features:
- Support N concurrent camera streams
- Isolated pipeline per camera
- Central event aggregation
- Per-camera health monitoring
- Graceful parallel shutdown

Copyright 2024 AegisAI Project
"""

import logging
import threading
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from aegis.video.rtsp_source import RTSPSource, CameraHealth, CameraStats
from aegis.utils.credentials import get_secure_logger

logger = get_secure_logger(__name__)


@dataclass
class CameraConfig:
    """Configuration for a single camera."""
    camera_id: str
    url: str
    name: Optional[str] = None
    location: Optional[str] = None
    enabled: bool = True
    connection_timeout: float = 5.0
    max_retries: int = 10
    
    def to_dict(self) -> dict:
        return {
            "camera_id": self.camera_id,
            "name": self.name or self.camera_id,
            "location": self.location,
            "enabled": self.enabled,
        }


@dataclass
class CameraEvent:
    """Event from a camera."""
    camera_id: str
    event_type: str  # "frame", "detection", "alert", "health_change"
    timestamp: datetime
    data: Any
    
    def to_dict(self) -> dict:
        return {
            "camera_id": self.camera_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data if not isinstance(self.data, np.ndarray) else "frame",
        }


class CameraManager:
    """
    Multi-camera orchestration with centralized monitoring.
    
    Manages multiple RTSP sources, provides health aggregation,
    and supports event-based callbacks for processing pipelines.
    
    Example:
        >>> manager = CameraManager()
        >>> manager.add_camera("cam1", "rtsp://192.168.1.100/stream")
        >>> manager.add_camera("cam2", "rtsp://192.168.1.101/stream")
        >>> manager.start_all()
        >>> 
        >>> for camera_id, frame in manager.get_frames():
        ...     process(camera_id, frame)
        >>> 
        >>> manager.stop_all()
    """
    
    def __init__(
        self,
        max_cameras: int = 16,
        on_event: Optional[Callable[[CameraEvent], None]] = None,
        on_health_change: Optional[Callable[[str, CameraHealth], None]] = None,
    ):
        """
        Initialize camera manager.
        
        Args:
            max_cameras: Maximum number of cameras to support
            on_event: Global event callback
            on_health_change: Camera health change callback
        """
        self._max_cameras = max_cameras
        self._on_event = on_event
        self._on_health_change = on_health_change
        
        self._cameras: Dict[str, RTSPSource] = {}
        self._configs: Dict[str, CameraConfig] = {}
        self._lock = threading.RLock()
        
        # Event aggregation
        self._event_queue: List[CameraEvent] = []
        self._event_lock = threading.Lock()
        
        # Thread pool for parallel processing
        self._executor = ThreadPoolExecutor(max_workers=max_cameras)
        
        logger.info(f"CameraManager initialized (max_cameras={max_cameras})")
    
    def add_camera(
        self,
        camera_id: str,
        url: str,
        name: Optional[str] = None,
        location: Optional[str] = None,
        enabled: bool = True,
        auto_start: bool = False,
        **kwargs
    ) -> bool:
        """
        Add a camera to the manager.
        
        Args:
            camera_id: Unique identifier for the camera
            url: RTSP URL
            name: Human-readable name
            location: Physical location description
            enabled: Whether camera should be active
            auto_start: Start capture immediately
            **kwargs: Additional RTSPSource configuration
            
        Returns:
            True if camera was added successfully
        """
        with self._lock:
            if camera_id in self._cameras:
                logger.warning(f"Camera {camera_id} already exists")
                return False
            
            if len(self._cameras) >= self._max_cameras:
                logger.error(f"Maximum cameras ({self._max_cameras}) reached")
                return False
            
            config = CameraConfig(
                camera_id=camera_id,
                url=url,
                name=name,
                location=location,
                enabled=enabled,
            )
            
            source = RTSPSource(
                camera_id=camera_id,
                url=url,
                on_health_change=self._handle_health_change,
                on_frame=self._handle_frame,
                **kwargs
            )
            
            self._cameras[camera_id] = source
            self._configs[camera_id] = config
            
            logger.info(f"Added camera: {camera_id} ({name or 'unnamed'})")
            
            if auto_start and enabled:
                source.start()
            
            return True
    
    def remove_camera(self, camera_id: str) -> bool:
        """
        Remove a camera from the manager.
        
        Args:
            camera_id: Camera to remove
            
        Returns:
            True if camera was removed
        """
        with self._lock:
            if camera_id not in self._cameras:
                logger.warning(f"Camera {camera_id} not found")
                return False
            
            source = self._cameras.pop(camera_id)
            source.stop()
            
            del self._configs[camera_id]
            
            logger.info(f"Removed camera: {camera_id}")
            return True
    
    def get_camera(self, camera_id: str) -> Optional[RTSPSource]:
        """Get camera source by ID."""
        return self._cameras.get(camera_id)
    
    def get_camera_stats(self, camera_id: str) -> Optional[CameraStats]:
        """Get statistics for a specific camera."""
        camera = self._cameras.get(camera_id)
        if camera:
            return camera.get_stats()
        return None
    
    def get_all_stats(self) -> Dict[str, CameraStats]:
        """Get statistics for all cameras."""
        return {
            camera_id: camera.get_stats()
            for camera_id, camera in self._cameras.items()
        }
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Get aggregated health summary."""
        stats = self.get_all_stats()
        
        up_count = sum(1 for s in stats.values() if s.health == CameraHealth.UP)
        degraded_count = sum(1 for s in stats.values() if s.health == CameraHealth.DEGRADED)
        down_count = sum(1 for s in stats.values() if s.health == CameraHealth.DOWN)
        
        total_fps = sum(s.fps for s in stats.values())
        
        return {
            "total_cameras": len(self._cameras),
            "cameras_up": up_count,
            "cameras_degraded": degraded_count,
            "cameras_down": down_count,
            "overall_health": "healthy" if down_count == 0 else "degraded" if up_count > 0 else "down",
            "total_fps": round(total_fps, 2),
            "cameras": {
                camera_id: stat.to_dict() 
                for camera_id, stat in stats.items()
            },
        }
    
    def list_cameras(self) -> List[Dict]:
        """List all configured cameras."""
        return [
            {
                **config.to_dict(),
                "health": self._cameras[camera_id].health.value,
            }
            for camera_id, config in self._configs.items()
        ]
    
    def start_camera(self, camera_id: str) -> bool:
        """Start a specific camera."""
        camera = self._cameras.get(camera_id)
        if camera:
            camera.start()
            return True
        return False
    
    def stop_camera(self, camera_id: str) -> bool:
        """Stop a specific camera."""
        camera = self._cameras.get(camera_id)
        if camera:
            camera.stop()
            return True
        return False
    
    def start_all(self):
        """Start all enabled cameras."""
        logger.info(f"Starting all cameras ({len(self._cameras)})")
        
        for camera_id, camera in self._cameras.items():
            config = self._configs.get(camera_id)
            if config and config.enabled:
                camera.start()
    
    def stop_all(self):
        """Stop all cameras gracefully."""
        logger.info(f"Stopping all cameras ({len(self._cameras)})")
        
        # Stop in parallel using thread pool
        futures = []
        for camera in self._cameras.values():
            futures.append(self._executor.submit(camera.stop))
        
        # Wait for all to complete
        for future in futures:
            try:
                future.result(timeout=5.0)
            except Exception as e:
                logger.error(f"Error stopping camera: {e}")
        
        logger.info("All cameras stopped")
    
    def get_frame(self, camera_id: str, timeout: float = 1.0) -> Optional[np.ndarray]:
        """Get frame from a specific camera."""
        camera = self._cameras.get(camera_id)
        if camera:
            return camera.get_frame(timeout)
        return None
    
    def get_frames(self, timeout: float = 0.1):
        """
        Generator yielding frames from all cameras.
        
        Yields:
            Tuple of (camera_id, frame) for each available frame
        """
        while True:
            frame_found = False
            
            for camera_id, camera in list(self._cameras.items()):
                frame = camera.get_frame(timeout=timeout)
                if frame is not None:
                    frame_found = True
                    yield camera_id, frame
            
            if not frame_found:
                break
    
    def _handle_health_change(self, camera_id: str, health: CameraHealth):
        """Handle health changes from cameras."""
        event = CameraEvent(
            camera_id=camera_id,
            event_type="health_change",
            timestamp=datetime.utcnow(),
            data={"health": health.value},
        )
        
        self._add_event(event)
        
        if self._on_health_change:
            try:
                self._on_health_change(camera_id, health)
            except Exception as e:
                logger.error(f"Health change callback error: {e}")
    
    def _handle_frame(self, camera_id: str, frame: np.ndarray):
        """Handle frames from cameras."""
        # Only add frame events if there's a listener
        if self._on_event:
            event = CameraEvent(
                camera_id=camera_id,
                event_type="frame",
                timestamp=datetime.utcnow(),
                data=frame,
            )
            self._add_event(event)
    
    def _add_event(self, event: CameraEvent):
        """Add event to queue and trigger callback."""
        with self._event_lock:
            self._event_queue.append(event)
            
            # Keep queue bounded
            if len(self._event_queue) > 1000:
                self._event_queue = self._event_queue[-500:]
        
        if self._on_event:
            try:
                self._on_event(event)
            except Exception as e:
                logger.error(f"Event callback error: {e}")
    
    def get_recent_events(self, limit: int = 100, event_type: Optional[str] = None) -> List[Dict]:
        """Get recent events, optionally filtered by type."""
        with self._event_lock:
            events = self._event_queue[-limit:]
            
            if event_type:
                events = [e for e in events if e.event_type == event_type]
            
            return [e.to_dict() for e in events]
    
    def shutdown(self):
        """Complete shutdown of manager and all resources."""
        logger.info("Shutting down CameraManager")
        
        self.stop_all()
        self._executor.shutdown(wait=True, cancel_futures=True)
        
        logger.info("CameraManager shutdown complete")
    
    def __enter__(self) -> 'CameraManager':
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown()
    
    def __len__(self) -> int:
        return len(self._cameras)
    
    def __repr__(self) -> str:
        health = self.get_health_summary()
        return f"CameraManager(cameras={len(self)}, up={health['cameras_up']}, down={health['cameras_down']})"
