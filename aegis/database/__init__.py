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
    Observation,
    RiskAssessment,
    Alert,
    OperationalAlert,
    AuditLog,
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
    ObservationRepository,
    RiskAssessmentRepository,
    BehavioralSessionRepository,
    TelemetryRepository,
    AnomalyRepository,
    AlertRepository,
    OperationalAlertRepository,
    AuditLogRepository,
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
    "Observation",
    "RiskAssessment",
    "Alert",
    "OperationalAlert",
    "AuditLog",
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
    "ObservationRepository",
    "RiskAssessmentRepository",
    "BehavioralSessionRepository",
    "TelemetryRepository",
    "AnomalyRepository",
    "AlertRepository",
    "OperationalAlertRepository",
    "AuditLogRepository",
    "NLQRepository",
    "InsightRepository",
    "ConsentRepository",
]
