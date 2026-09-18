"""Best-effort durable audit logging for operational actions.

Audit availability must not block surveillance, evidence capture, alerting, or
operator acknowledgement.  Failures are logged locally and callers continue
their authoritative workflow.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

logger = logging.getLogger(__name__)


def record_audit(
    action: str,
    *,
    actor_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[Mapping[str, Any]] = None,
) -> bool:
    """Append a non-sensitive audit record without affecting the caller.

    Callers must provide summaries only; this function deliberately does not
    accept raw credentials, agent prompts, evidence payloads, or camera URLs.
    """
    try:
        from aegis.database.connection import get_db_session
        from aegis.database.repositories import AuditLogRepository

        with get_db_session() as session:
            AuditLogRepository(session).append(
                action=action,
                actor_id=actor_id,
                resource_type=resource_type,
                resource_id=resource_id,
                details=dict(details or {}),
            )
        return True
    except Exception as exc:
        logger.warning("Operational audit write failed action=%s error=%s", action, type(exc).__name__)
        return False
