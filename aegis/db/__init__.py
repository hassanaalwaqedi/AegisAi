"""
AegisAI - Database Module (DEPRECATED)

DEPRECATION NOTICE: This package is superseded by ``aegis.database``.
All new code should use ``aegis.database`` directly.

This module remains for backward compatibility only. It re-exports from
``aegis.database`` where possible, but will be removed in a future version.
"""

import warnings

warnings.warn(
    "aegis.db is deprecated. Use aegis.database instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export from the canonical aegis.database package
from aegis.database.connection import (  # noqa: F401
    Base,
    get_engine,
    get_session,
    create_tables as init_db,
)
from aegis.database.models import (  # noqa: F401
    Event as EventModel,
    Alert as AlertModel,
)
from aegis.database.repositories import (  # noqa: F401
    EventRepository,
    AlertRepository,
)

__all__ = [
    "init_db",
    "get_engine",
    "get_session",
    "Base",
    "EventModel",
    "AlertModel",
    "EventRepository",
    "AlertRepository",
]
