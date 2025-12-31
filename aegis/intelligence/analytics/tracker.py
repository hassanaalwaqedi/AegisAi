"""
Behavioral Analytics Tracker - Database Connected
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
from sqlalchemy.orm import Session

from aegis.database import BehavioralSessionRepository, get_db_session
from aegis.database.models import BehavioralSession


class UserIntent(Enum):
    EXPLORING = "exploring"
    COMPARING = "comparing"
    DECIDING = "deciding"
    CONFUSED = "confused"
    FRUSTRATED = "frustrated"
    ENGAGED = "engaged"


@dataclass
class BehaviorEvent:
    event_type: str
    timestamp: datetime
    session_id: str
    properties: dict = field(default_factory=dict)


class BehavioralTracker:
    """Tracks and analyzes user behavioral patterns with database persistence."""
    
    def __init__(self, db: Session = None):
        self._db = db
    
    def _get_repo(self, db: Session = None) -> BehavioralSessionRepository:
        return BehavioralSessionRepository(db or self._db)
    
    def track_event(self, event: BehaviorEvent, db: Session = None) -> None:
        """Track a behavioral event and persist to database."""
        repo = self._get_repo(db)
        repo.add_event(event.session_id, event.event_type, event.properties)
        
        # Update session based on event type
        updates = {}
        if event.event_type == "scroll_depth":
            depth = event.properties.get("depth", 0)
            updates["scroll_depth_max"] = depth
        elif event.event_type == "rage_click":
            session = repo.get_or_create(event.session_id)
            updates["rage_clicks"] = (session.rage_clicks or 0) + 1
        elif event.event_type == "hesitation":
            session = repo.get_or_create(event.session_id)
            updates["hesitation_count"] = (session.hesitation_count or 0) + 1
        elif event.event_type == "page_view":
            session = repo.get_or_create(event.session_id)
            path = event.properties.get("path", "")
            decision_path = session.decision_path or []
            decision_path.append(path)
            updates["decision_path"] = decision_path
        
        if updates:
            updates["intent"] = self._calculate_intent(repo.get_or_create(event.session_id), updates)
            repo.update(event.session_id, **updates)
    
    def _calculate_intent(self, session: BehavioralSession, updates: dict) -> str:
        """Calculate user intent from behavioral signals."""
        rage = updates.get("rage_clicks", session.rage_clicks or 0)
        hesitation = updates.get("hesitation_count", session.hesitation_count or 0)
        scroll = updates.get("scroll_depth_max", session.scroll_depth_max or 0)
        path_len = len(updates.get("decision_path", session.decision_path or []))
        event_count = session.event_count or 0
        
        if rage >= 3:
            return UserIntent.FRUSTRATED.value
        if hesitation >= 3:
            return UserIntent.CONFUSED.value
        if path_len >= 5:
            return UserIntent.COMPARING.value
        if scroll >= 0.9:
            return UserIntent.ENGAGED.value
        if event_count < 5:
            return UserIntent.EXPLORING.value
        return UserIntent.DECIDING.value
    
    def get_session_summary(self, session_id: str, db: Session = None) -> dict:
        """Get summary of session behavior."""
        repo = self._get_repo(db)
        session = repo.get_or_create(session_id)
        return session.to_dict()
