"""Process-local telemetry for the active ``aegis.database`` persistence path.

This is intentionally telemetry, not another persistence implementation.  It
lets the operational context report a failed write instead of silently
presenting an apparently healthy database-backed view.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PersistenceStatus:
    """Thread-safe status of writes attempted through ``aegis.database``."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._attempted = 0
        self._succeeded = 0
        self._failed = 0
        self._last_success_at: Optional[datetime] = None
        self._last_failure_at: Optional[datetime] = None
        self._last_failure_reason: Optional[str] = None
        self._last_source: Optional[str] = None

    def record_success(self, source: str) -> None:
        with self._lock:
            self._attempted += 1
            self._succeeded += 1
            self._last_success_at = _utcnow()
            self._last_source = source

    def record_failure(self, source: str, error: Exception | str) -> None:
        with self._lock:
            self._attempted += 1
            self._failed += 1
            self._last_failure_at = _utcnow()
            self._last_failure_reason = str(error)
            self._last_source = source

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "attempted": self._attempted,
                "succeeded": self._succeeded,
                "failed": self._failed,
                "last_success_at": self._last_success_at,
                "last_failure_at": self._last_failure_at,
                "last_failure_reason": self._last_failure_reason,
                "last_source": self._last_source,
            }

    def reset(self) -> None:
        with self._lock:
            self._attempted = 0
            self._succeeded = 0
            self._failed = 0
            self._last_success_at = None
            self._last_failure_at = None
            self._last_failure_reason = None
            self._last_source = None


_persistence_status = PersistenceStatus()


def get_persistence_status() -> PersistenceStatus:
    """Return telemetry for the one active database repository stack."""

    return _persistence_status


def reset_persistence_status() -> None:
    """Reset telemetry; intended for tests and controlled process reset."""

    _persistence_status.reset()


def check_event_persistence_ready() -> Tuple[bool, Optional[str]]:
    """Verify the active event repository can write without creating an event.

    A database ``SELECT 1`` only proves connectivity. This probe exercises the
    same repository and INSERT path used for risk-alert persistence inside a
    savepoint that is explicitly rolled back. It never commits or displays a
    synthetic security event.
    """
    try:
        from aegis.database.connection import get_db_session
        from aegis.database.repositories import EventRepository

        with get_db_session() as session:
            savepoint = session.begin_nested()
            try:
                EventRepository(session).create(
                    event_type="persistence_readiness_probe",
                    message="Aegis persistence readiness probe",
                    timestamp=_utcnow(),
                    metadata={"internal": True},
                )
                session.flush()
            finally:
                savepoint.rollback()
        return True, None
    except Exception as exc:
        # Avoid returning a database URL, credentials, or raw driver payload
        # through an operator-facing context endpoint.
        return False, f"Database-backed event persistence readiness failed: {type(exc).__name__}."
