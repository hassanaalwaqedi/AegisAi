"""
AegisAI - Smart City Risk Intelligence System
API Module - Shared State

This module provides thread-safe shared state for the API.
Stores current system status, tracks, and events.

Phase 4: Response & Productization Layer
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from collections import deque


@dataclass
class SystemStatus:
    """
    Current system status.
    
    Attributes:
        running: Whether processing is active
        start_time: When system started
        frames_processed: Total frames processed
        current_fps: Current processing FPS
        active_tracks: Number of active tracks
        total_detections: Total detections count
        total_anomalies: Total anomalies detected
        max_risk_level: Highest current risk level
    """
    running: bool = False
    start_time: Optional[datetime] = None
    frames_processed: int = 0
    current_fps: float = 0.0
    active_tracks: int = 0
    total_detections: int = 0
    total_anomalies: int = 0
    total_alerts: int = 0
    high_risk_count: int = 0
    max_risk_level: str = "LOW"
    max_risk_score: float = 0.0
    model_name: str = ""
    supported_classes: List[str] = field(default_factory=list)
    weapon_detection_supported: bool = False
    person_detector: Dict[str, Any] = field(default_factory=dict)
    weapon_detector: Dict[str, Any] = field(default_factory=dict)
    action_recognition_supported: bool = False
    pose_estimation_supported: bool = False
    semantic_verification_supported: bool = False

    def __post_init__(self) -> None:
        try:
            from config import DetectionConfig

            config = DetectionConfig()
            class_names = dict(config.CLASS_NAMES)
            target_classes = tuple(config.target_classes)
            person_supported = [
                class_names.get(class_id, f"class_{class_id}")
                for class_id in sorted(set(target_classes))
            ]
            weapon_supported = list(config.weapon_model_class_names.values())
            self.model_name = config.model_path
            self.supported_classes = [*person_supported, *weapon_supported]
            self.weapon_detection_supported = Path(config.weapon_model_path).exists()
            self.person_detector = {
                "model_name": config.model_path,
                "supported_classes": person_supported,
            }
            self.weapon_detector = {
                "model_name": config.weapon_model_path,
                "supported_classes": weapon_supported,
                "internal_class_ids": {
                    name: int(config.weapon_internal_class_ids[source_id])
                    for source_id, name in config.weapon_model_class_names.items()
                },
                "weapon_detection_supported": self.weapon_detection_supported,
            }
        except Exception:
            pass
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        uptime = 0
        if self.start_time:
            uptime = (datetime.now() - self.start_time).total_seconds()
        
        return {
            "running": self.running,
            "uptime_seconds": round(uptime, 1),
            "frames_processed": self.frames_processed,
            "current_fps": round(self.current_fps, 1),
            "active_tracks": self.active_tracks,
            "total_detections": self.total_detections,
            "total_anomalies": self.total_anomalies,
            "total_alerts": self.total_alerts,
            "high_risk_count": self.high_risk_count,
            "max_risk_level": self.max_risk_level,
            "max_risk_score": round(self.max_risk_score, 3),
            "model_name": self.model_name,
            "supported_classes": self.supported_classes,
            "weapon_detection_supported": self.weapon_detection_supported,
            "person_detector": self.person_detector,
            "weapon_detector": self.weapon_detector,
            "action_recognition_supported": self.action_recognition_supported,
            "pose_estimation_supported": self.pose_estimation_supported,
            "semantic_verification_supported": self.semantic_verification_supported
        }


@dataclass
class TrackInfo:
    """
    Information about an active track.
    
    Attributes:
        track_id: Unique track identifier
        class_name: Object class (Person, Car, etc.)
        risk_level: Current risk level
        risk_score: Current risk score
        zone: Current zone
        behaviors: Active behaviors
        time_tracked: Duration tracked
    """
    track_id: Union[int, str]
    class_name: str = "Unknown"
    object_category: str = "generic"
    is_person: bool = False
    is_vehicle: bool = False
    is_weapon: bool = False
    camera_id: Optional[str] = None
    confidence: Optional[float] = None
    bbox: Optional[List[float]] = None
    first_seen: Optional[str] = None
    total_seen_count: int = 0
    confidence_history: List[float] = field(default_factory=list)
    risk_level: str = "LOW"
    risk_score: float = 0.0
    zone: str = ""
    behaviors: List[str] = field(default_factory=list)
    risk_explanation: Optional[str] = None
    detected_classes: List[str] = field(default_factory=list)
    evidence_type: str = "object_detection"
    model_source: List[str] = field(default_factory=list)
    verification_status: str = "confirmed"
    reason_codes: List[str] = field(default_factory=list)
    visual_evidence: Dict[str, Any] = field(default_factory=dict)
    weapon_class: Optional[str] = None
    weapon_confidence: Optional[float] = None
    person_track_id: Optional[Union[int, str]] = None
    weapon_track_id: Optional[Union[int, str]] = None
    association_type: Optional[str] = None
    association_score: Optional[float] = None
    stable_frames: int = 0
    evidence_objects: List[Dict[str, Any]] = field(default_factory=list)
    movement_state: Optional[str] = None
    time_tracked: float = 0.0
    last_seen: Optional[str] = None
    last_updated: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "track_id": self.track_id,
            "class_name": self.class_name,
            "object_category": self.object_category,
            "is_person": self.is_person,
            "is_vehicle": self.is_vehicle,
            "is_weapon": self.is_weapon,
            "camera_id": self.camera_id,
            "confidence": self.confidence,
            "bbox": self.bbox,
            "first_seen": self.first_seen,
            "duration_seconds": self._duration_seconds(),
            "total_seen_count": self.total_seen_count,
            "confidence_history": self.confidence_history[-20:],
            "risk_level": self.risk_level,
            "risk_score": round(self.risk_score, 3),
            "zone": self.zone,
            "behaviors": self.behaviors,
            "risk_explanation": self.risk_explanation,
            "detected_classes": self.detected_classes,
            "evidence_type": self.evidence_type,
            "model_source": self.model_source,
            "verification_status": self.verification_status,
            "reason_codes": self.reason_codes,
            "visual_evidence": self.visual_evidence,
            "weapon_class": self.weapon_class,
            "weapon_confidence": self.weapon_confidence,
            "person_track_id": self.person_track_id,
            "weapon_track_id": self.weapon_track_id,
            "association_type": self.association_type,
            "association_score": round(self.association_score, 3) if self.association_score is not None else None,
            "stable_frames": self.stable_frames,
            "evidence_objects": self.evidence_objects,
            "movement_state": self.movement_state,
            "time_tracked": round(self.time_tracked, 1),
            "last_seen": self.last_seen,
            "last_updated": self.last_updated.isoformat()
        }

    def to_registry_dict(self) -> dict:
        """Convert to object registry representation."""
        return {
            "track_id": self.track_id,
            "camera_id": self.camera_id,
            "class_name": self.class_name,
            "confidence": self.confidence,
            "confidence_history": self.confidence_history[-20:],
            "bbox": self.bbox,
            "object_category": self.object_category,
            "is_person": self.is_person,
            "is_vehicle": self.is_vehicle,
            "is_weapon": self.is_weapon,
            "model_source": self.model_source,
            "verification_status": self.verification_status,
            "weapon_class": self.weapon_class,
            "weapon_confidence": self.weapon_confidence,
            "person_track_id": self.person_track_id,
            "weapon_track_id": self.weapon_track_id,
            "association_type": self.association_type,
            "association_score": round(self.association_score, 3) if self.association_score is not None else None,
            "stable_frames": self.stable_frames,
            "evidence_objects": self.evidence_objects,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "duration_seconds": self._duration_seconds(),
            "total_seen_count": self.total_seen_count,
        }

    def _duration_seconds(self) -> float:
        if not self.first_seen:
            return round(float(self.time_tracked or 0.0), 2)
        try:
            first = datetime.fromisoformat(self.first_seen)
            last = datetime.fromisoformat(self.last_seen) if self.last_seen else self.last_updated
            return round(max((last - first).total_seconds(), 0.0), 2)
        except Exception:
            return round(float(self.time_tracked or 0.0), 2)


class APIState:
    """
    Thread-safe shared state for the API.
    
    Stores current system status, active tracks, events, and statistics.
    All access is protected by a lock for thread safety.
    
    Example:
        >>> state = APIState()
        >>> state.update_status(frames=100, fps=30.0)
        >>> status = state.get_status()
    """
    
    def __init__(self):
        """Initialize API state."""
        self._lock = threading.RLock()
        self._status = SystemStatus()
        self._tracks: Dict[Union[int, str], TrackInfo] = {}
        self._events: deque = deque(maxlen=100)
        self._statistics: Dict[str, Any] = {}
    
    def start(self) -> None:
        """Mark system as started."""
        with self._lock:
            self._status.running = True
            self._status.start_time = datetime.now()
    
    def stop(self) -> None:
        """Mark system as stopped."""
        with self._lock:
            self._status.running = False
    
    def update_status(
        self,
        frames: Optional[int] = None,
        fps: Optional[float] = None,
        active_tracks: Optional[int] = None,
        detections: Optional[int] = None,
        anomalies: Optional[int] = None,
        total_alerts: Optional[int] = None,
        high_risk_count: Optional[int] = None,
        max_risk_level: Optional[str] = None,
        max_risk_score: Optional[float] = None,
        model_name: Optional[str] = None,
        supported_classes: Optional[List[str]] = None,
        weapon_detection_supported: Optional[bool] = None,
        person_detector: Optional[Dict[str, Any]] = None,
        weapon_detector: Optional[Dict[str, Any]] = None,
        action_recognition_supported: Optional[bool] = None,
        pose_estimation_supported: Optional[bool] = None,
        semantic_verification_supported: Optional[bool] = None
    ) -> None:
        """
        Update system status.
        
        Args:
            frames: Frames processed
            fps: Current FPS
            active_tracks: Active track count
            detections: Total detections
            anomalies: Total anomalies
            max_risk_level: Highest risk level
            max_risk_score: Highest risk score
        """
        with self._lock:
            if frames is not None:
                self._status.frames_processed = frames
            if fps is not None:
                self._status.current_fps = fps
            if active_tracks is not None:
                self._status.active_tracks = active_tracks
            if detections is not None:
                self._status.total_detections = detections
            if anomalies is not None:
                self._status.total_anomalies = anomalies
            if total_alerts is not None:
                self._status.total_alerts = total_alerts
            if high_risk_count is not None:
                self._status.high_risk_count = high_risk_count
            if max_risk_level is not None:
                self._status.max_risk_level = max_risk_level
            if max_risk_score is not None:
                self._status.max_risk_score = max_risk_score
            if model_name is not None:
                self._status.model_name = model_name
            if supported_classes is not None:
                self._status.supported_classes = supported_classes
            if weapon_detection_supported is not None:
                self._status.weapon_detection_supported = weapon_detection_supported
            if person_detector is not None:
                self._status.person_detector = person_detector
            if weapon_detector is not None:
                self._status.weapon_detector = weapon_detector
            if action_recognition_supported is not None:
                self._status.action_recognition_supported = action_recognition_supported
            if pose_estimation_supported is not None:
                self._status.pose_estimation_supported = pose_estimation_supported
            if semantic_verification_supported is not None:
                self._status.semantic_verification_supported = semantic_verification_supported
    
    def get_status(self) -> dict:
        """Get current system status as dictionary."""
        with self._lock:
            return self._status.to_dict()
    
    def update_track(
        self,
        track_id: Union[int, str],
        class_name: str = "Unknown",
        object_category: str = "generic",
        is_person: bool = False,
        is_vehicle: bool = False,
        is_weapon: bool = False,
        risk_level: str = "LOW",
        risk_score: float = 0.0,
        zone: str = "",
        behaviors: Optional[List[str]] = None,
        time_tracked: float = 0.0,
        camera_id: Optional[str] = None,
        confidence: Optional[float] = None,
        bbox: Optional[List[float]] = None,
        risk_explanation: Optional[str] = None,
        detected_classes: Optional[List[str]] = None,
        evidence_type: str = "object_detection",
        model_source: Optional[List[str]] = None,
        verification_status: str = "confirmed",
        reason_codes: Optional[List[str]] = None,
        visual_evidence: Optional[Dict[str, Any]] = None,
        weapon_class: Optional[str] = None,
        weapon_confidence: Optional[float] = None,
        person_track_id: Optional[Union[int, str]] = None,
        weapon_track_id: Optional[Union[int, str]] = None,
        association_type: Optional[str] = None,
        association_score: Optional[float] = None,
        stable_frames: int = 0,
        evidence_objects: Optional[List[Dict[str, Any]]] = None,
        movement_state: Optional[str] = None,
        last_seen: Optional[str] = None
    ) -> None:
        """Update or add a track."""
        with self._lock:
            existing = self._tracks.get(track_id)
            first_seen = existing.first_seen if existing and existing.first_seen else (last_seen or datetime.now().isoformat())
            total_seen_count = (existing.total_seen_count if existing else 0) + 1
            confidence_history = list(existing.confidence_history if existing else [])
            if confidence is not None:
                confidence_history.append(float(confidence))
            confidence_history = confidence_history[-50:]
            self._tracks[track_id] = TrackInfo(
                track_id=track_id,
                class_name=class_name,
                object_category=object_category,
                is_person=is_person,
                is_vehicle=is_vehicle,
                is_weapon=is_weapon,
                camera_id=camera_id,
                confidence=confidence,
                bbox=bbox,
                first_seen=first_seen,
                total_seen_count=total_seen_count,
                confidence_history=confidence_history,
                risk_level=risk_level,
                risk_score=risk_score,
                zone=zone,
                behaviors=behaviors or [],
                risk_explanation=risk_explanation,
                detected_classes=detected_classes or [],
                evidence_type=evidence_type,
                model_source=model_source or [],
                verification_status=verification_status,
                reason_codes=reason_codes or [],
                visual_evidence=visual_evidence or {},
                weapon_class=weapon_class,
                weapon_confidence=weapon_confidence,
                person_track_id=person_track_id,
                weapon_track_id=weapon_track_id,
                association_type=association_type,
                association_score=association_score,
                stable_frames=stable_frames,
                evidence_objects=evidence_objects or [],
                movement_state=movement_state,
                time_tracked=time_tracked,
                last_seen=last_seen,
                last_updated=datetime.now()
            )
    
    def remove_track(self, track_id: Union[int, str]) -> None:
        """Remove a track."""
        with self._lock:
            if track_id in self._tracks:
                del self._tracks[track_id]
    
    def get_tracks(self, min_risk_level: Optional[str] = None) -> List[dict]:
        """
        Get active tracks.
        
        Args:
            min_risk_level: Filter by minimum risk level
            
        Returns:
            List of track dictionaries
        """
        level_priority = {"LOW": 1, "CANDIDATE_MEDIUM": 2, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
        min_priority = level_priority.get(min_risk_level, 0) if min_risk_level else 0
        
        with self._lock:
            tracks = []
            for track in self._tracks.values():
                track_priority = level_priority.get(track.risk_level, 0)
                if track_priority >= min_priority:
                    tracks.append(track.to_dict())
            return sorted(tracks, key=lambda t: -t["risk_score"])

    def get_object_registry(self, camera_id: Optional[str] = None) -> List[dict]:
        """Get active object registry entries, optionally filtered by camera."""
        with self._lock:
            entries = []
            for track in self._tracks.values():
                if camera_id and track.camera_id != camera_id:
                    continue
                entries.append(track.to_registry_dict())
            return sorted(entries, key=lambda item: str(item.get("last_seen") or ""), reverse=True)
    
    def add_event(self, event: dict) -> None:
        """Add an event to the event log."""
        with self._lock:
            self._events.append(event)
    
    def get_events(self, limit: int = 20) -> List[dict]:
        """Get recent events."""
        with self._lock:
            return list(self._events)[-limit:]
    
    def update_statistics(
        self,
        person_count: int = 0,
        vehicle_count: int = 0,
        weapon_count: int = 0,
        active_detections_count: int = 0,
        detections_by_class: Optional[Dict[str, int]] = None,
        crowd_detected: bool = False,
        max_density: int = 0,
        risk_distribution: Optional[Dict[str, int]] = None,
        association_count: int = 0,
        critical_association_count: int = 0
    ) -> None:
        """Update crowd and risk statistics."""
        with self._lock:
            self._statistics = {
                "person_count": person_count,
                "vehicle_count": vehicle_count,
                "weapon_count": weapon_count,
                "active_detections_count": active_detections_count,
                "detections_by_class": detections_by_class or {},
                "crowd_detected": crowd_detected,
                "max_density": max_density,
                "association_count": association_count,
                "critical_association_count": critical_association_count,
                "risk_distribution": risk_distribution or {
                    "LOW": 0, "CANDIDATE_MEDIUM": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0
                },
                "timestamp": datetime.now().isoformat()
            }
    
    def get_statistics(self) -> dict:
        """Get current statistics."""
        with self._lock:
            return self._statistics.copy()
    
    def cleanup_stale_tracks(self, max_age_seconds: float = 5.0) -> int:
        """Remove tracks not updated recently."""
        with self._lock:
            now = datetime.now()
            stale = [
                tid for tid, track in self._tracks.items()
                if (now - track.last_updated).total_seconds() > max_age_seconds
            ]
            for tid in stale:
                del self._tracks[tid]
            return len(stale)
    
    def reset(self) -> None:
        """Reset all state."""
        with self._lock:
            self._status = SystemStatus()
            self._tracks.clear()
            self._events.clear()
            self._statistics.clear()


# Global singleton instance
_state: Optional[APIState] = None


def get_state() -> APIState:
    """Get the global API state singleton."""
    global _state
    if _state is None:
        _state = APIState()
    return _state
