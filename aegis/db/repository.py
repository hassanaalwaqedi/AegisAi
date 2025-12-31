"""
AegisAI - Database Repository Layer
Data Access Pattern for Events, Alerts, and Tracks

Provides clean CRUD operations with automatic cleanup
of old records based on retention policy.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import desc

from aegis.db.models import EventModel, AlertModel, TrackSnapshotModel

# Configure module logger
logger = logging.getLogger(__name__)


class EventRepository:
    """
    Repository for risk events.
    
    Example:
        with get_session() as session:
            repo = EventRepository(session)
            repo.create_event(
                track_id=5,
                risk_score=0.85,
                risk_level="CRITICAL",
                explanation="Loitering in restricted zone"
            )
    """
    
    def __init__(self, session: Session):
        self._session = session
    
    def create_event(
        self,
        track_id: int,
        risk_score: float,
        risk_level: str,
        frame_id: Optional[int] = None,
        class_name: Optional[str] = None,
        zone_name: Optional[str] = None,
        factors: Optional[List[dict]] = None,
        explanation: Optional[str] = None
    ) -> EventModel:
        """
        Create a new event record.
        
        Returns:
            Created EventModel
        """
        event = EventModel(
            track_id=track_id,
            frame_id=frame_id,
            risk_score=risk_score,
            risk_level=risk_level,
            class_name=class_name,
            zone_name=zone_name,
            factors=factors,
            explanation=explanation
        )
        
        self._session.add(event)
        self._session.flush()  # Get ID without commit
        
        logger.debug(f"Created event {event.event_id} for track {track_id}")
        return event
    
    def get_by_id(self, event_id: str) -> Optional[EventModel]:
        """Get event by event_id."""
        return self._session.query(EventModel).filter(
            EventModel.event_id == event_id
        ).first()
    
    def get_recent(
        self,
        limit: int = 100,
        min_level: Optional[str] = None
    ) -> List[EventModel]:
        """
        Get recent events, optionally filtered by level.
        
        Args:
            limit: Maximum events to return
            min_level: Minimum risk level (HIGH, CRITICAL)
            
        Returns:
            List of EventModel, newest first
        """
        query = self._session.query(EventModel)
        
        if min_level:
            level_order = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
            if min_level in level_order:
                min_idx = level_order.index(min_level)
                allowed = level_order[min_idx:]
                query = query.filter(EventModel.risk_level.in_(allowed))
        
        return query.order_by(desc(EventModel.timestamp)).limit(limit).all()
    
    def get_by_track(
        self,
        track_id: int,
        limit: int = 50
    ) -> List[EventModel]:
        """Get events for a specific track."""
        return self._session.query(EventModel).filter(
            EventModel.track_id == track_id
        ).order_by(desc(EventModel.timestamp)).limit(limit).all()
    
    def cleanup_old(self, retention_days: int = 30) -> int:
        """
        Delete events older than retention period.
        
        Returns:
            Number of events deleted
        """
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        
        count = self._session.query(EventModel).filter(
            EventModel.created_at < cutoff
        ).delete()
        
        if count > 0:
            logger.info(f"Cleaned up {count} events older than {retention_days} days")
        
        return count
    
    def count(self) -> int:
        """Get total event count."""
        return self._session.query(EventModel).count()


class AlertRepository:
    """
    Repository for alerts.
    
    Example:
        with get_session() as session:
            repo = AlertRepository(session)
            alert = repo.create_alert(
                track_id=5,
                level="CRITICAL",
                risk_score=0.85,
                message="Alert: High risk loitering detected"
            )
    """
    
    def __init__(self, session: Session):
        self._session = session
    
    def create_alert(
        self,
        track_id: int,
        level: str,
        risk_score: float,
        message: str,
        event_id: Optional[str] = None,
        zone: Optional[str] = None,
        factors: Optional[List[str]] = None
    ) -> AlertModel:
        """Create a new alert record."""
        alert = AlertModel(
            track_id=track_id,
            level=level,
            risk_score=risk_score,
            message=message,
            event_id=event_id,
            zone=zone,
            factors=factors
        )
        
        self._session.add(alert)
        self._session.flush()
        
        logger.debug(f"Created alert {alert.alert_id} for track {track_id}")
        return alert
    
    def get_by_id(self, alert_id: str) -> Optional[AlertModel]:
        """Get alert by alert_id."""
        return self._session.query(AlertModel).filter(
            AlertModel.alert_id == alert_id
        ).first()
    
    def get_unacknowledged(self, limit: int = 100) -> List[AlertModel]:
        """Get unacknowledged alerts."""
        return self._session.query(AlertModel).filter(
            AlertModel.acknowledged == False
        ).order_by(desc(AlertModel.created_at)).limit(limit).all()
    
    def get_recent(self, limit: int = 100) -> List[AlertModel]:
        """Get recent alerts."""
        return self._session.query(AlertModel).order_by(
            desc(AlertModel.created_at)
        ).limit(limit).all()
    
    def acknowledge(
        self,
        alert_id: str,
        acknowledged_by: Optional[str] = None
    ) -> bool:
        """
        Acknowledge an alert.
        
        Returns:
            True if acknowledged, False if not found
        """
        alert = self.get_by_id(alert_id)
        
        if not alert:
            return False
        
        alert.acknowledged = True
        alert.acknowledged_at = datetime.utcnow()
        alert.acknowledged_by = acknowledged_by
        
        logger.info(f"Alert {alert_id} acknowledged by {acknowledged_by or 'system'}")
        return True
    
    def cleanup_old(self, retention_days: int = 30) -> int:
        """Delete alerts older than retention period."""
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        
        count = self._session.query(AlertModel).filter(
            AlertModel.created_at < cutoff
        ).delete()
        
        if count > 0:
            logger.info(f"Cleaned up {count} alerts older than {retention_days} days")
        
        return count
    
    def count(self) -> int:
        """Get total alert count."""
        return self._session.query(AlertModel).count()
    
    def count_unacknowledged(self) -> int:
        """Get unacknowledged alert count."""
        return self._session.query(AlertModel).filter(
            AlertModel.acknowledged == False
        ).count()


class TrackRepository:
    """
    Repository for track snapshots.
    
    Stores periodic snapshots for historical analysis.
    """
    
    def __init__(self, session: Session):
        self._session = session
    
    def create_snapshot(
        self,
        track_id: int,
        frame_id: int,
        class_name: Optional[str] = None,
        confidence: Optional[float] = None,
        bbox: Optional[tuple] = None,
        speed: Optional[float] = None,
        direction: Optional[float] = None,
        risk_score: Optional[float] = None,
        behaviors: Optional[List[str]] = None,
        semantic_label: Optional[str] = None,
        semantic_confidence: Optional[float] = None
    ) -> TrackSnapshotModel:
        """Create a track snapshot."""
        snapshot = TrackSnapshotModel(
            track_id=track_id,
            frame_id=frame_id,
            class_name=class_name,
            confidence=confidence,
            bbox_x1=bbox[0] if bbox else None,
            bbox_y1=bbox[1] if bbox else None,
            bbox_x2=bbox[2] if bbox else None,
            bbox_y2=bbox[3] if bbox else None,
            speed=speed,
            direction=direction,
            risk_score=risk_score,
            behaviors=behaviors,
            semantic_label=semantic_label,
            semantic_confidence=semantic_confidence
        )
        
        self._session.add(snapshot)
        self._session.flush()
        
        return snapshot
    
    def get_track_history(
        self,
        track_id: int,
        limit: int = 100
    ) -> List[TrackSnapshotModel]:
        """Get historical snapshots for a track."""
        return self._session.query(TrackSnapshotModel).filter(
            TrackSnapshotModel.track_id == track_id
        ).order_by(desc(TrackSnapshotModel.timestamp)).limit(limit).all()
    
    def cleanup_old(self, retention_days: int = 7) -> int:
        """Delete old snapshots (shorter retention for volume)."""
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        
        count = self._session.query(TrackSnapshotModel).filter(
            TrackSnapshotModel.created_at < cutoff
        ).delete()
        
        if count > 0:
            logger.info(f"Cleaned up {count} track snapshots older than {retention_days} days")
        
        return count
    
    def count(self) -> int:
        """Get total snapshot count."""
        return self._session.query(TrackSnapshotModel).count()
