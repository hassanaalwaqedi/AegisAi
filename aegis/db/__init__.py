"""
AegisAI - Database Module
Persistence Layer for Events, Alerts, and Tracks

Provides SQLAlchemy-based persistence with support for:
- SQLite (default, zero-config)
- PostgreSQL (production, via DATABASE_URL)

Usage:
    from aegis.db import init_db, get_session, EventRepository, AlertRepository
    
    # Initialize database
    init_db()
    
    # Use repositories
    with get_session() as session:
        repo = EventRepository(session)
        repo.create_event(...)
"""

from aegis.db.database import (
    init_db,
    get_engine,
    get_session,
    Base
)
from aegis.db.models import (
    EventModel,
    AlertModel,
    TrackSnapshotModel
)
from aegis.db.repository import (
    EventRepository,
    AlertRepository,
    TrackRepository
)

__all__ = [
    # Database
    "init_db",
    "get_engine",
    "get_session",
    "Base",
    # Models
    "EventModel",
    "AlertModel",
    "TrackSnapshotModel",
    # Repositories
    "EventRepository",
    "AlertRepository",
    "TrackRepository",
]
