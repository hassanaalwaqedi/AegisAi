"""
AegisAI - Database Module

PostgreSQL database connection and ORM models.
"""

from .connection import (
    Base,
    get_database_url,
    init_engine,
    get_engine,
    get_session,
    get_db_session,
    create_tables,
    check_connection,
)

from .models import (
    Event,
    Alert,
    TrackStats,
    SessionRecord,
    BehavioralSession,
    BehaviorEvent,
    BehaviorEmbedding,
    TelemetrySpan,
    TelemetryMetric,
    Anomaly,
    SmartAlertRecord,
    NLQQuery,
    InsightRecord,
    ConsentRecord,
)

from .repositories import (
    EventRepository,
    BehavioralSessionRepository,
    TelemetryRepository,
    AnomalyRepository,
    AlertRepository,
    NLQRepository,
    InsightRepository,
    ConsentRepository,
)

__all__ = [
    # Connection
    "Base",
    "get_database_url",
    "init_engine",
    "get_engine",
    "get_session",
    "get_db_session",
    "create_tables",
    "check_connection",
    # Models
    "Event",
    "Alert",
    "TrackStats",
    "SessionRecord",
    "BehavioralSession",
    "BehaviorEvent",
    "BehaviorEmbedding",
    "TelemetrySpan",
    "TelemetryMetric",
    "Anomaly",
    "SmartAlertRecord",
    "NLQQuery",
    "InsightRecord",
    "ConsentRecord",
    # Repositories
    "EventRepository",
    "BehavioralSessionRepository",
    "TelemetryRepository",
    "AnomalyRepository",
    "AlertRepository",
    "NLQRepository",
    "InsightRepository",
    "ConsentRepository",
]
