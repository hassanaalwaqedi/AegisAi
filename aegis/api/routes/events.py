"""
AegisAI - Smart City Risk Intelligence System
API Routes - Events Endpoint

GET /events - Recent risk events and alerts

Phase 4: Response & Productization Layer
"""

import logging
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from aegis.api.state import get_state
from aegis.intelligence.event_access import load_persisted_event_records, merge_event_records

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/events", tags=["events"])

_SNAPSHOT_ROOT = Path("data/output/snapshots")


class IncidentLifecycleUpdate(BaseModel):
    """An operator lifecycle decision for a durable incident."""

    status: Literal["open", "acknowledged", "under_review", "resolved", "false_positive"]
    reason: Optional[str] = Field(default=None, max_length=1000)


def _operator_actor(actor: Optional[str]) -> str:
    """Use a gateway-provided actor label without pretending it authenticates one."""
    normalized = str(actor or "").strip()
    return normalized[:160] if normalized else "api-key-operator"


def _audit(
    action: str,
    *,
    actor: Optional[str],
    resource_type: str,
    resource_id: str,
    details: Optional[dict] = None,
) -> None:
    from aegis.audit import record_audit

    record_audit(
        action,
        actor_id=_operator_actor(actor),
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
    )


def _evidence_payload(event) -> dict:
    """Return the durable evidence projection without internal ORM details."""
    payload = event.to_dict()
    payload["snapshot_available"] = event.snapshot_status == "saved" and bool(event.snapshot_path)
    payload["snapshot_url"] = (
        f"/events/evidence/{event.event_id}/snapshot" if payload["snapshot_available"] else None
    )
    return payload


def _load_evidence(*, event_id: Optional[str] = None, alert_id: Optional[str] = None):
    try:
        from aegis.database.connection import get_db_session
        from aegis.database.repositories import EventRepository

        with get_db_session() as session:
            repository = EventRepository(session)
            if event_id is not None:
                return repository.get_by_event_id(event_id)
            return repository.get_by_alert_id(str(alert_id))
    except Exception as exc:
        logger.warning("Durable evidence lookup failed: %s", exc)
        raise HTTPException(status_code=503, detail="Durable evidence is temporarily unavailable.") from exc


def _incident_payload(incident) -> dict:
    """Public incident projection containing only durable correlation facts."""
    return incident.to_dict()


def _load_incident(incident_id: str):
    try:
        from aegis.database.connection import get_db_session
        from aegis.database.repositories import IncidentRepository

        with get_db_session() as session:
            return IncidentRepository(session).get_by_incident_id(incident_id)
    except Exception as exc:
        logger.warning("Incident lookup failed: %s", exc)
        raise HTTPException(status_code=503, detail="Incident correlation is temporarily unavailable.") from exc


@router.get("")
async def get_events(
    limit: int = Query(default=20, ge=1, le=100, description="Max events to return"),
    level: Optional[str] = Query(default=None, description="Filter by risk level")
):
    """
    Get recent risk events.
    
    Args:
        limit: Maximum number of events to return
        level: Filter by risk level (LOW, MEDIUM, HIGH, CRITICAL)
    
    Returns:
        List of recent events
    """
    state = get_state()
    runtime_events = state.get_events(limit=100)
    try:
        persisted_events = load_persisted_event_records(limit=100)
    except Exception as exc:
        logger.warning("Durable event history unavailable: %s", type(exc).__name__)
        persisted_events = []
    events = merge_event_records(persisted_events, runtime_events, limit=limit)
    
    # Filter by level if specified
    if level:
        level_upper = level.upper()
        events = [e for e in events if e.get("risk_level") == level_upper]
    
    return {
        "count": len(events),
        "events": events
    }


@router.get("/persisted")
async def get_persisted_evidence(
    limit: int = Query(default=20, ge=1, le=100, description="Max durable evidence records to return"),
    level: Optional[str] = Query(default=None, description="Filter by durable risk level"),
):
    """Return recent persisted alert evidence, including records from before restart."""
    try:
        from aegis.database.connection import get_db_session
        from aegis.database.repositories import EventRepository

        with get_db_session() as session:
            events = EventRepository(session).get_recent_evidence(limit=limit, risk_level=level)
            evidence = [_evidence_payload(event) for event in events]
    except Exception as exc:
        logger.warning("Recent durable evidence lookup failed: %s", exc)
        raise HTTPException(status_code=503, detail="Durable evidence is temporarily unavailable.") from exc

    return {"count": len(evidence), "evidence": evidence}


@router.get("/incidents")
async def get_active_incidents(
    limit: int = Query(default=20, ge=1, le=100, description="Max active incidents to return"),
):
    """Return active, durable incident timelines without mutating them on read."""
    try:
        from aegis.database.connection import get_db_session
        from aegis.database.repositories import IncidentRepository

        with get_db_session() as session:
            incidents = IncidentRepository(session).list_active(limit=limit)
            payload = [_incident_payload(incident) for incident in incidents]
    except Exception as exc:
        logger.warning("Active incident lookup failed: %s", exc)
        raise HTTPException(status_code=503, detail="Incident correlation is temporarily unavailable.") from exc
    return {"count": len(payload), "incidents": payload}


@router.get("/incidents/recent")
async def get_recent_incidents(
    limit: int = Query(default=20, ge=1, le=100, description="Max recent incidents to return"),
):
    """Return recent active and resolved incidents from the durable store."""
    try:
        from aegis.database.connection import get_db_session
        from aegis.database.repositories import IncidentRepository

        with get_db_session() as session:
            incidents = IncidentRepository(session).list_recent(limit=limit)
            payload = [_incident_payload(incident) for incident in incidents]
    except Exception as exc:
        logger.warning("Recent incident lookup failed: %s", exc)
        raise HTTPException(status_code=503, detail="Incident correlation is temporarily unavailable.") from exc
    return {"count": len(payload), "incidents": payload}


@router.patch("/incidents/{incident_id}/status")
async def update_incident_lifecycle(
    incident_id: str,
    update: IncidentLifecycleUpdate,
    x_aegis_actor: Optional[str] = Header(default=None),
):
    """Apply an explicit, durable operator lifecycle decision to an incident."""
    try:
        from aegis.database.connection import get_db_session
        from aegis.database.repositories import IncidentRepository

        with get_db_session() as session:
            incident = IncidentRepository(session).set_lifecycle_status(
                incident_id,
                update.status,
                actor_id=_operator_actor(x_aegis_actor),
                reason=update.reason,
            )
            if incident is None:
                raise HTTPException(status_code=404, detail="Incident not found.")
            payload = _incident_payload(incident)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.warning("Incident lifecycle update failed: %s", exc)
        raise HTTPException(status_code=503, detail="Incident lifecycle is temporarily unavailable.") from exc

    _audit(
        "incident.lifecycle_changed",
        actor=x_aegis_actor,
        resource_type="incident",
        resource_id=incident_id,
        details={"status": update.status, "reason_provided": bool(update.reason and update.reason.strip())},
    )
    return payload


@router.get("/incidents/{incident_id}/timeline")
async def get_incident_timeline(incident_id: str, x_aegis_actor: Optional[str] = Header(default=None)):
    """Return the real persisted events that form one incident timeline."""
    incident = _load_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    try:
        from aegis.database.connection import get_db_session
        from aegis.database.repositories import EventRepository

        with get_db_session() as session:
            events = EventRepository(session).get_by_incident_id(incident_id)
            payload = [_evidence_payload(event) for event in events]
    except Exception as exc:
        logger.warning("Incident timeline lookup failed: %s", exc)
        raise HTTPException(status_code=503, detail="Incident timeline is temporarily unavailable.") from exc
    _audit(
        "incident.timeline_accessed",
        actor=x_aegis_actor,
        resource_type="incident",
        resource_id=incident_id,
        details={"event_count": len(payload)},
    )
    return {"incident": _incident_payload(incident), "count": len(payload), "events": payload}


@router.get("/incidents/{incident_id}/evidence")
async def get_incident_evidence(incident_id: str, x_aegis_actor: Optional[str] = Header(default=None)):
    """Return the evidence records linked to one incident."""
    timeline = await get_incident_timeline(incident_id, None)
    _audit(
        "evidence.incident_accessed",
        actor=x_aegis_actor,
        resource_type="incident",
        resource_id=incident_id,
        details={"evidence_count": timeline["count"]},
    )
    return {
        "incident": timeline["incident"],
        "count": timeline["count"],
        "evidence": timeline["events"],
    }


@router.get("/incidents/{incident_id}/assessments")
async def get_incident_assessments(incident_id: str, x_aegis_actor: Optional[str] = Header(default=None)):
    """Return explainable, versioned risk assessments for one incident."""
    incident = _load_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    try:
        from aegis.database.connection import get_db_session
        from aegis.database.repositories import RiskAssessmentRepository

        with get_db_session() as session:
            assessments = [
                assessment.to_dict()
                for assessment in RiskAssessmentRepository(session).list_for_incident(incident_id)
            ]
    except Exception as exc:
        logger.warning("Incident assessment lookup failed: %s", exc)
        raise HTTPException(status_code=503, detail="Incident assessments are temporarily unavailable.") from exc
    _audit(
        "incident.assessments_accessed",
        actor=x_aegis_actor,
        resource_type="incident",
        resource_id=incident_id,
        details={"assessment_count": len(assessments)},
    )
    return {"incident": _incident_payload(incident), "count": len(assessments), "assessments": assessments}


@router.get("/incidents/{incident_id}")
async def get_incident(incident_id: str):
    incident = _load_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    return _incident_payload(incident)


@router.get("/evidence/alert/{alert_id}")
async def get_evidence_by_alert_id(alert_id: str, x_aegis_actor: Optional[str] = Header(default=None)):
    event = _load_evidence(alert_id=alert_id)
    if event is None:
        raise HTTPException(status_code=404, detail="No durable evidence exists for this alert.")
    _audit(
        "evidence.alert_accessed",
        actor=x_aegis_actor,
        resource_type="evidence",
        resource_id=event.event_id,
        details={"alert_id": alert_id},
    )
    return _evidence_payload(event)


@router.get("/evidence/{event_id}/snapshot")
async def get_evidence_snapshot(event_id: str, x_aegis_actor: Optional[str] = Header(default=None)):
    """Serve an authenticated evidence keyframe only from the snapshot root."""
    event = _load_evidence(event_id=event_id)
    if event is None or event.snapshot_status != "saved" or not event.snapshot_path:
        raise HTTPException(status_code=404, detail="No saved snapshot exists for this evidence record.")

    root = _SNAPSHOT_ROOT.resolve()
    candidate = Path(event.snapshot_path).resolve()
    if candidate != root and root not in candidate.parents:
        logger.warning("Rejected invalid evidence snapshot path for event_id=%s", event_id)
        raise HTTPException(status_code=404, detail="Evidence snapshot is unavailable.")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="Evidence snapshot is unavailable.")
    _audit(
        "evidence.snapshot_accessed",
        actor=x_aegis_actor,
        resource_type="evidence",
        resource_id=event_id,
        details={"snapshot_status": event.snapshot_status},
    )
    return FileResponse(candidate, media_type="image/jpeg", filename=candidate.name)


@router.get("/evidence/{event_id}")
async def get_evidence_by_event_id(event_id: str, x_aegis_actor: Optional[str] = Header(default=None)):
    event = _load_evidence(event_id=event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="No durable evidence exists for this event.")
    _audit(
        "evidence.record_accessed",
        actor=x_aegis_actor,
        resource_type="evidence",
        resource_id=event_id,
        details={"snapshot_status": event.snapshot_status},
    )
    return _evidence_payload(event)
