"""Read-only access to the unified operational event history.

Camera ingestion keeps a small in-process buffer for low-latency UI updates,
while confirmed high-risk evidence is stored durably in ``aegis.database``.
This module deliberately exposes only a normalized, public event projection so
Intelligence consumers can query both sources without getting direct database
handles or internal ORM objects.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence


def _as_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def event_identity(record: Mapping[str, Any]) -> Optional[str]:
    """Return the stable public identity used for cross-source deduplication."""
    for key in ("event_id", "id"):
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def persisted_event_record(event: Any) -> dict[str, Any]:
    """Convert a durable ``Event`` ORM row into the runtime event contract."""
    metadata = getattr(event, "event_metadata", None)
    record = dict(metadata) if isinstance(metadata, Mapping) else {}
    event_id = str(getattr(event, "event_id", None) or getattr(event, "id", "")).strip()
    timestamp = getattr(event, "timestamp", None) or getattr(event, "created_at", None)
    timestamp_value = timestamp.isoformat() if isinstance(timestamp, datetime) else timestamp
    risk_level = getattr(event, "risk_level", None)
    reason = getattr(event, "reason", None) or getattr(event, "message", None)

    # Canonical persisted fields override stale or incomplete JSON metadata.
    record.update(
        {
            "id": event_id,
            "event_id": event_id,
            "evidence_id": event_id,
            "evidence_status": "persisted",
            "alert_id": getattr(event, "alert_id", None) or record.get("alert_id"),
            "incident_id": getattr(event, "incident_id", None) or record.get("incident_id"),
            "type": getattr(event, "event_type", None),
            "event_type": getattr(event, "event_type", None),
            "camera_id": getattr(event, "camera_id", None) or record.get("camera_id") or getattr(event, "zone", None),
            "camera_name": getattr(event, "camera_name", None) or record.get("camera_name"),
            "track_id": getattr(event, "track_key", None) or getattr(event, "track_id", None) or record.get("track_id"),
            "timestamp": timestamp_value,
            "severity": risk_level,
            "risk_level": risk_level,
            "risk_score": getattr(event, "risk_score", None),
            "object_class": getattr(event, "object_class", None),
            "class_name": getattr(event, "object_class", None) or record.get("class_name"),
            "bbox": getattr(event, "bounding_box", None),
            "reason": reason,
            "description": reason,
            "explanation": reason,
            "factors": getattr(event, "factors", None) or record.get("factors") or [],
            "zone": getattr(event, "zone", None),
            "zone_id": getattr(event, "zone_id", None),
            "zone_name": getattr(event, "zone_name", None),
            "snapshot_status": getattr(event, "snapshot_status", None) or "unavailable",
            "data": dict(metadata) if isinstance(metadata, Mapping) else {},
            "persisted": True,
        }
    )
    return record


def load_persisted_event_records(limit: int = 100) -> list[dict[str, Any]]:
    """Load recent durable evidence as safe, serializable event records.

    Callers intentionally receive data, not a database session.  Failures are
    allowed to propagate so each API can truthfully choose a degraded fallback.
    """
    from aegis.database.connection import get_db_session
    from aegis.database.repositories import EventRepository

    bounded_limit = max(1, min(int(limit), 500))
    with get_db_session() as session:
        repository = EventRepository(session)
        # ``get_recent`` remains as a compatibility fallback for older
        # repository implementations and focused tests.
        reader = getattr(repository, "get_recent_evidence", None)
        rows = reader(limit=bounded_limit) if callable(reader) else repository.get_recent(limit=bounded_limit)
        return [persisted_event_record(row) for row in rows]


def merge_event_records(
    *sources: Sequence[Mapping[str, Any]],
    limit: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Merge sources by public event ID, retaining the newest stable ordering.

    Sources later in the argument list override matching fields.  This lets a
    live buffer add acknowledgement or just-created evidence fields over the
    durable record without inventing a second event identity.
    """
    keyed: dict[str, dict[str, Any]] = {}
    anonymous: list[dict[str, Any]] = []
    for source in sources:
        for raw in source:
            if not isinstance(raw, Mapping):
                continue
            record = dict(raw)
            key = event_identity(record)
            if key is None:
                anonymous.append(record)
                continue
            if key in keyed:
                keyed[key].update(record)
            else:
                keyed[key] = record

    def sort_key(record: Mapping[str, Any]) -> tuple[int, str, str]:
        timestamp = _as_datetime(record.get("timestamp"))
        return (
            1 if timestamp is not None else 0,
            timestamp.isoformat() if timestamp is not None else "",
            event_identity(record) or "",
        )

    records = [*keyed.values(), *anonymous]
    records.sort(key=sort_key)
    if limit is not None:
        records = records[-max(0, int(limit)):]
    return records
