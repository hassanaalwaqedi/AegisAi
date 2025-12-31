"""
AegisAI - Database Repository

Repository pattern implementations for data access.

Sprint 2: Production Hardening
"""

import json
import logging
from datetime import datetime
from typing import List, Optional

from aegis.database.connection import Database, get_database
from aegis.database.models import Event, Alert, TrackStats, SessionStats, EventType

# Configure module logger
logger = logging.getLogger(__name__)


class EventRepository:
    """
    Repository for Event persistence.
    
    Handles CRUD operations for events.
    """
    
    def __init__(self, database: Optional[Database] = None):
        """Initialize repository with database."""
        self._db = database or get_database()
    
    def save(self, event: Event) -> int:
        """
        Save event to database.
        
        Args:
            event: Event to save
            
        Returns:
            Event ID
        """
        with self._db.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO events (event_type, timestamp, track_id, risk_level, 
                                   risk_score, message, factors, zone, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_type.value,
                    event.timestamp.isoformat(),
                    event.track_id,
                    event.risk_level,
                    event.risk_score,
                    event.message,
                    event.factors,
                    event.zone,
                    event.metadata
                )
            )
            conn.commit()
            event.id = cursor.lastrowid
            return event.id
    
    def get_by_id(self, event_id: int) -> Optional[Event]:
        """Get event by ID."""
        with self._db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM events WHERE id = ?",
                (event_id,)
            ).fetchone()
            
            if row:
                return self._row_to_event(row)
            return None
    
    def get_recent(self, limit: int = 50) -> List[Event]:
        """Get recent events."""
        with self._db.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM events ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()
            
            return [self._row_to_event(row) for row in rows]
    
    def get_by_risk_level(self, level: str, limit: int = 50) -> List[Event]:
        """Get events by risk level."""
        with self._db.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE risk_level = ? ORDER BY timestamp DESC LIMIT ?",
                (level, limit)
            ).fetchall()
            
            return [self._row_to_event(row) for row in rows]
    
    def get_by_track(self, track_id: int) -> List[Event]:
        """Get all events for a track."""
        with self._db.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE track_id = ? ORDER BY timestamp DESC",
                (track_id,)
            ).fetchall()
            
            return [self._row_to_event(row) for row in rows]
    
    def count_by_level(self) -> dict:
        """Count events by risk level."""
        with self._db.connection() as conn:
            rows = conn.execute(
                """
                SELECT risk_level, COUNT(*) as count 
                FROM events 
                WHERE risk_level IS NOT NULL 
                GROUP BY risk_level
                """
            ).fetchall()
            
            return {row["risk_level"]: row["count"] for row in rows}
    
    def _row_to_event(self, row) -> Event:
        """Convert database row to Event."""
        return Event(
            id=row["id"],
            event_type=EventType(row["event_type"]),
            timestamp=datetime.fromisoformat(row["timestamp"]),
            track_id=row["track_id"],
            risk_level=row["risk_level"],
            risk_score=row["risk_score"],
            message=row["message"],
            factors=row["factors"],
            zone=row["zone"],
            metadata=row["metadata"]
        )


class AlertRepository:
    """
    Repository for Alert persistence.
    """
    
    def __init__(self, database: Optional[Database] = None):
        """Initialize repository with database."""
        self._db = database or get_database()
    
    def save(self, alert: Alert) -> int:
        """Save alert to database."""
        with self._db.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO alerts (event_id, level, acknowledged, 
                                   acknowledged_at, acknowledged_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    alert.event_id,
                    alert.level,
                    1 if alert.acknowledged else 0,
                    alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
                    alert.acknowledged_by,
                    alert.created_at.isoformat()
                )
            )
            conn.commit()
            alert.id = cursor.lastrowid
            return alert.id
    
    def acknowledge(self, alert_id: int, user: str = "system") -> bool:
        """Mark alert as acknowledged."""
        with self._db.connection() as conn:
            conn.execute(
                """
                UPDATE alerts 
                SET acknowledged = 1, acknowledged_at = ?, acknowledged_by = ?
                WHERE id = ?
                """,
                (datetime.now().isoformat(), user, alert_id)
            )
            conn.commit()
            return True
    
    def get_unacknowledged(self, limit: int = 50) -> List[Alert]:
        """Get unacknowledged alerts."""
        with self._db.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM alerts 
                WHERE acknowledged = 0 
                ORDER BY created_at DESC LIMIT ?
                """,
                (limit,)
            ).fetchall()
            
            return [self._row_to_alert(row) for row in rows]
    
    def get_by_level(self, level: str, limit: int = 50) -> List[Alert]:
        """Get alerts by level."""
        with self._db.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM alerts WHERE level = ? ORDER BY created_at DESC LIMIT ?",
                (level, limit)
            ).fetchall()
            
            return [self._row_to_alert(row) for row in rows]
    
    def _row_to_alert(self, row) -> Alert:
        """Convert database row to Alert."""
        return Alert(
            id=row["id"],
            event_id=row["event_id"],
            level=row["level"],
            acknowledged=bool(row["acknowledged"]),
            acknowledged_at=datetime.fromisoformat(row["acknowledged_at"]) if row["acknowledged_at"] else None,
            acknowledged_by=row["acknowledged_by"],
            created_at=datetime.fromisoformat(row["created_at"])
        )


class StatsRepository:
    """
    Repository for statistics persistence.
    """
    
    def __init__(self, database: Optional[Database] = None):
        """Initialize repository with database."""
        self._db = database or get_database()
    
    def save_track_stats(self, stats: TrackStats) -> None:
        """Save or update track statistics."""
        with self._db.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO track_stats 
                (track_id, class_name, first_seen, last_seen, 
                 total_frames, max_risk_score, behaviors_detected)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stats.track_id,
                    stats.class_name,
                    stats.first_seen.isoformat(),
                    stats.last_seen.isoformat(),
                    stats.total_frames,
                    stats.max_risk_score,
                    stats.behaviors_detected
                )
            )
            conn.commit()
    
    def get_track_stats(self, track_id: int) -> Optional[TrackStats]:
        """Get statistics for a track."""
        with self._db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM track_stats WHERE track_id = ?",
                (track_id,)
            ).fetchone()
            
            if row:
                return TrackStats(
                    track_id=row["track_id"],
                    class_name=row["class_name"],
                    first_seen=datetime.fromisoformat(row["first_seen"]),
                    last_seen=datetime.fromisoformat(row["last_seen"]),
                    total_frames=row["total_frames"],
                    max_risk_score=row["max_risk_score"],
                    behaviors_detected=row["behaviors_detected"]
                )
            return None
    
    def start_session(self) -> int:
        """Start a new processing session."""
        with self._db.connection() as conn:
            cursor = conn.execute(
                "INSERT INTO sessions (start_time) VALUES (?)",
                (datetime.now().isoformat(),)
            )
            conn.commit()
            return cursor.lastrowid
    
    def end_session(self, session_id: int, stats: dict) -> None:
        """End a session with final statistics."""
        with self._db.connection() as conn:
            conn.execute(
                """
                UPDATE sessions 
                SET end_time = ?, total_frames = ?, total_detections = ?,
                    total_tracks = ?, total_alerts = ?, avg_fps = ?
                WHERE id = ?
                """,
                (
                    datetime.now().isoformat(),
                    stats.get("total_frames", 0),
                    stats.get("total_detections", 0),
                    stats.get("unique_tracks", 0),
                    stats.get("total_alerts", 0),
                    stats.get("avg_fps", 0.0),
                    session_id
                )
            )
            conn.commit()
    
    def get_daily_summary(self) -> dict:
        """Get summary statistics for today."""
        today = datetime.now().date().isoformat()
        
        with self._db.connection() as conn:
            # Events today
            event_count = conn.execute(
                "SELECT COUNT(*) FROM events WHERE date(timestamp) = ?",
                (today,)
            ).fetchone()[0]
            
            # Alerts by level
            alerts = conn.execute(
                """
                SELECT level, COUNT(*) as count 
                FROM alerts 
                WHERE date(created_at) = ?
                GROUP BY level
                """,
                (today,)
            ).fetchall()
            
            return {
                "date": today,
                "total_events": event_count,
                "alerts_by_level": {row["level"]: row["count"] for row in alerts}
            }
