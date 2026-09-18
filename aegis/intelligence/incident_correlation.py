"""Lightweight, evidence-backed incident correlation for durable risk events.

This module deliberately consumes persisted event facts only.  It does not
score detections, create artificial timeline entries, or infer a relationship
when an event has no useful identity or severity.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from aegis.database.models import Event, Incident
from aegis.database.repositories import IncidentRepository


CORRELATION_WINDOW = timedelta(minutes=3)
INCIDENT_IDLE_TIMEOUT = timedelta(minutes=5)
_RISK_RANK = {"MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: object) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _risk_level(value: object) -> Optional[str]:
    normalized = str(value or "").strip().upper()
    return normalized if normalized in _RISK_RANK else None


def _risk_score(value: object) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _append_unique(current: Iterable[object] | None, value: Optional[str]) -> list[str]:
    values = [str(item) for item in (current or []) if str(item).strip()]
    if value and value not in values:
        values.append(value)
    return values


def _merge_factors(*collections: object) -> list[str]:
    values: list[str] = []
    for collection in collections:
        if not isinstance(collection, (list, tuple, set)):
            continue
        for value in collection:
            text = str(value).strip()
            if text and text not in values:
                values.append(text)
    return values


class IncidentCorrelationService:
    """Correlate eligible durable events into short-lived incident timelines."""

    def __init__(
        self,
        session: Session,
        *,
        now=_utcnow,
        correlation_window: timedelta = CORRELATION_WINDOW,
        idle_timeout: timedelta = INCIDENT_IDLE_TIMEOUT,
    ) -> None:
        self._repository = IncidentRepository(session)
        self._now = now
        self._correlation_window = correlation_window
        self._idle_timeout = idle_timeout

    def correlate_event(self, event: Event) -> Optional[Incident]:
        """Attach one evidence record to its active incident when justified.

        An event without a durable ID, camera, clear MEDIUM/HIGH/CRITICAL
        level, timestamp, or track/zone association is left unlinked.  That is
        safer than creating a low-confidence incident from incomplete data.
        """
        observed_at = _as_utc(event.timestamp)
        risk_level = _risk_level(event.risk_level)
        camera_id = str(event.camera_id or "").strip()
        if not event.event_id or not observed_at or not camera_id or not risk_level:
            return None
        if not event.track_key and not event.zone_id:
            return None

        current_time = _as_utc(self._now()) or _utcnow()
        self.resolve_expired(now=current_time)

        if event.incident_id:
            existing = self._repository.get_by_incident_id(event.incident_id)
            if existing is not None:
                return existing

        incident = self._find_candidate(
            camera_id=camera_id,
            track_key=event.track_key,
            zone_id=event.zone_id,
            risk_level=risk_level,
            observed_at=observed_at,
        )
        created = incident is None
        if incident is None:
            incident = Incident(
                incident_id=f"inc-{uuid.uuid4().hex}",
                camera_id=camera_id,
                primary_track_id=event.track_key,
                related_track_ids=[],
                zone_id=event.zone_id,
                zone_name=event.zone_name,
                start_time=observed_at,
                last_seen_time=observed_at,
                current_risk_level=risk_level,
                max_risk_score=_risk_score(event.risk_score),
                status="active",
                lifecycle_status="open",
                event_ids=[],
                alert_ids=[],
                evidence_ids=[],
                risk_types=[],
                summary_reason=event.reason or event.message,
                contributing_factors=[],
            )
            self._repository.add(incident)

        self._attach_event(incident, event, observed_at, risk_level)
        # A newly-created incident is flushed by ``add``; existing records need
        # an explicit flush so callers can safely commit and publish its ID.
        if not created:
            self._repository.db.flush()
        return incident

    def resolve_expired(self, *, now: Optional[datetime] = None) -> int:
        current_time = _as_utc(now or self._now()) or _utcnow()
        return self._repository.resolve_expired(
            cutoff=current_time - self._idle_timeout,
            resolved_at=current_time,
        )

    def _find_candidate(
        self,
        *,
        camera_id: str,
        track_key: Optional[str],
        zone_id: Optional[str],
        risk_level: str,
        observed_at: datetime,
    ) -> Optional[Incident]:
        candidates = self._repository.get_active_candidates(
            camera_id=camera_id,
            since=observed_at - self._correlation_window,
        )
        matches: list[tuple[int, datetime, Incident]] = []
        for candidate in candidates:
            last_seen = _as_utc(candidate.last_seen_time)
            if not last_seen or abs(last_seen - observed_at) > self._correlation_window:
                continue
            if track_key and candidate.primary_track_id == track_key:
                matches.append((0, last_seen, candidate))
                continue
            if track_key and track_key in (candidate.related_track_ids or []):
                matches.append((1, last_seen, candidate))
                continue
            # A zone-only link is deliberately narrower: same camera + exact
            # zone + close severity. This supports a multi-track zone incident
            # without merging unrelated activity in the same camera.
            current_level = _risk_level(candidate.current_risk_level)
            if (
                zone_id
                and candidate.zone_id == zone_id
                and current_level
                and abs(_RISK_RANK[current_level] - _RISK_RANK[risk_level]) <= 1
            ):
                matches.append((2, last_seen, candidate))
        if not matches:
            return None
        matches.sort(key=lambda item: (item[0], -item[1].timestamp(), item[2].incident_id))
        return matches[0][2]

    def _attach_event(
        self,
        incident: Incident,
        event: Event,
        observed_at: datetime,
        risk_level: str,
    ) -> None:
        previous_rank = _RISK_RANK.get(_risk_level(incident.current_risk_level) or "", 0)
        incoming_rank = _RISK_RANK[risk_level]
        incoming_score = _risk_score(event.risk_score)

        incident.start_time = min(_as_utc(incident.start_time) or observed_at, observed_at)
        incident.last_seen_time = max(_as_utc(incident.last_seen_time) or observed_at, observed_at)
        incident.event_ids = _append_unique(incident.event_ids, event.event_id)
        incident.evidence_ids = _append_unique(incident.evidence_ids, event.event_id)
        incident.alert_ids = _append_unique(incident.alert_ids, event.alert_id)
        incident.risk_types = _append_unique(incident.risk_types, event.event_type)
        if event.track_key and event.track_key != incident.primary_track_id:
            incident.related_track_ids = _append_unique(incident.related_track_ids, event.track_key)
        if not incident.primary_track_id and event.track_key:
            incident.primary_track_id = event.track_key
        if not incident.zone_id and event.zone_id:
            incident.zone_id = event.zone_id
            incident.zone_name = event.zone_name
        if incoming_score is not None:
            incident.max_risk_score = max(
                _risk_score(incident.max_risk_score) if incident.max_risk_score is not None else incoming_score,
                incoming_score,
            )
        # Do not lower the displayed level because a subsequent event was less
        # severe.  A stronger event may update the summary with its real reason.
        if incoming_rank >= previous_rank:
            incident.current_risk_level = risk_level
            if event.reason or event.message:
                incident.summary_reason = event.reason or event.message
        metadata = event.event_metadata if isinstance(event.event_metadata, dict) else {}
        related_track_ids = metadata.get("related_track_ids")
        if not isinstance(related_track_ids, (list, tuple, set)):
            related_track_ids = []
        nearby_person_track_id = metadata.get("nearby_person_track_id")
        if nearby_person_track_id and not related_track_ids:
            related_track_ids = [*related_track_ids, nearby_person_track_id]
        for related_track_id in related_track_ids:
            related = str(related_track_id).strip()
            if related and related != incident.primary_track_id:
                incident.related_track_ids = _append_unique(incident.related_track_ids, related)
        incident.contributing_factors = _merge_factors(
            incident.contributing_factors,
            event.factors,
            metadata.get("reason_codes"),
        )
        # This is the correlation worker's liveness marker, not the operator
        # lifecycle.  Do not erase acknowledgement/review decisions as more
        # real evidence arrives for the same active incident.
        incident.status = "active"
        incident.updated_at = _as_utc(self._now()) or _utcnow()
        event.incident_id = incident.incident_id
