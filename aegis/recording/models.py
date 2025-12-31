"""
AegisAI - Recording Event Models

Metadata storage for recorded risk events.

Copyright 2024 AegisAI Project
"""

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
import threading
import logging

logger = logging.getLogger(__name__)


@dataclass
class RecordingEvent:
    """
    Metadata for a recorded risk event.
    
    Attributes:
        event_id: Unique identifier (UUID)
        camera_id: Source camera identifier
        start_time: Recording start timestamp
        end_time: Recording end timestamp
        max_risk_score: Highest risk score during event
        detected_object_types: List of detected class names
        file_path: Path to MP4 file
        duration_seconds: Recording duration
        trigger_risk_score: Risk score that triggered recording
    """
    event_id: str
    camera_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    max_risk_score: float = 0.0
    detected_object_types: List[str] = field(default_factory=list)
    file_path: str = ""
    duration_seconds: float = 0.0
    trigger_risk_score: float = 0.0
    
    @classmethod
    def create(cls, camera_id: str, trigger_score: float) -> 'RecordingEvent':
        """Create a new recording event."""
        return cls(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            camera_id=camera_id,
            start_time=datetime.now(),
            trigger_risk_score=trigger_score,
            max_risk_score=trigger_score,
        )
    
    def finalize(self, file_path: str) -> None:
        """Finalize the event with end time and file path."""
        self.end_time = datetime.now()
        self.file_path = file_path
        if self.start_time and self.end_time:
            self.duration_seconds = (self.end_time - self.start_time).total_seconds()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "event_id": self.event_id,
            "camera_id": self.camera_id,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "max_risk_score": round(self.max_risk_score, 3),
            "detected_object_types": list(set(self.detected_object_types)),
            "file_path": self.file_path,
            "duration_seconds": round(self.duration_seconds, 2),
            "trigger_risk_score": round(self.trigger_risk_score, 3),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RecordingEvent':
        """Create from dictionary."""
        return cls(
            event_id=data["event_id"],
            camera_id=data["camera_id"],
            start_time=datetime.fromisoformat(data["start_time"]) if data.get("start_time") else datetime.now(),
            end_time=datetime.fromisoformat(data["end_time"]) if data.get("end_time") else None,
            max_risk_score=data.get("max_risk_score", 0.0),
            detected_object_types=data.get("detected_object_types", []),
            file_path=data.get("file_path", ""),
            duration_seconds=data.get("duration_seconds", 0.0),
            trigger_risk_score=data.get("trigger_risk_score", 0.0),
        )


class RecordingMetadata:
    """
    Persistent storage for recording event metadata.
    
    Uses JSON file for simplicity (no DB dependency).
    Thread-safe for concurrent access.
    """
    
    def __init__(self, storage_path: str = "data/recordings/metadata.json"):
        """Initialize metadata storage."""
        self._storage_path = Path(storage_path)
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._events: Dict[str, RecordingEvent] = {}
        self._load()
    
    def _load(self) -> None:
        """Load events from storage."""
        if self._storage_path.exists():
            try:
                with open(self._storage_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for evt_data in data.get("events", []):
                        evt = RecordingEvent.from_dict(evt_data)
                        self._events[evt.event_id] = evt
                logger.info(f"Loaded {len(self._events)} recording events")
            except Exception as e:
                logger.error(f"Failed to load metadata: {e}")
    
    def _save(self) -> None:
        """Save events to storage atomically."""
        temp_path = self._storage_path.with_suffix('.tmp')
        try:
            data = {
                "version": "1.0",
                "updated_at": datetime.now().isoformat(),
                "events": [e.to_dict() for e in self._events.values()]
            }
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            temp_path.replace(self._storage_path)
        except Exception as e:
            logger.error(f"Failed to save metadata: {e}")
            if temp_path.exists():
                temp_path.unlink()
    
    def add(self, event: RecordingEvent) -> None:
        """Add or update a recording event."""
        with self._lock:
            self._events[event.event_id] = event
            self._save()
    
    def get(self, event_id: str) -> Optional[RecordingEvent]:
        """Get event by ID."""
        with self._lock:
            return self._events.get(event_id)
    
    def list_events(
        self,
        camera_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        min_risk: float = 0.0,
        limit: int = 100
    ) -> List[RecordingEvent]:
        """
        List events with optional filters.
        
        Args:
            camera_id: Filter by camera
            start_date: Filter by start date (inclusive)
            end_date: Filter by end date (inclusive)
            min_risk: Minimum risk score
            limit: Maximum events to return
        """
        with self._lock:
            events = list(self._events.values())
        
        # Apply filters
        if camera_id:
            events = [e for e in events if e.camera_id == camera_id]
        if start_date:
            events = [e for e in events if e.start_time >= start_date]
        if end_date:
            events = [e for e in events if e.start_time <= end_date]
        if min_risk > 0:
            events = [e for e in events if e.max_risk_score >= min_risk]
        
        # Sort by start time descending
        events.sort(key=lambda e: e.start_time, reverse=True)
        
        return events[:limit]
    
    def delete(self, event_id: str) -> bool:
        """Delete an event."""
        with self._lock:
            if event_id in self._events:
                del self._events[event_id]
                self._save()
                return True
            return False
    
    @property
    def count(self) -> int:
        """Total number of recorded events."""
        with self._lock:
            return len(self._events)
