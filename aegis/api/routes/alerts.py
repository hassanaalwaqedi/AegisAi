"""
AegisAI - Alert API Routes

REST endpoints for alert management and acknowledgment.

Copyright 2024 AegisAI Project
"""

from fastapi import APIRouter, HTTPException, Depends, Header, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from aegis.api.security import verify_api_key
from aegis.alerts import AlertManager, Alert, AlertSummary

router = APIRouter(prefix="/alerts", tags=["alerts"])


# Global alert manager reference - set by app on startup
_alert_manager: Optional[AlertManager] = None


def get_alert_manager() -> AlertManager:
    """Get the global alert manager instance."""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
    return _alert_manager


def set_alert_manager(manager: AlertManager):
    """Set the global alert manager instance."""
    global _alert_manager
    _alert_manager = manager


class AlertResponse(BaseModel):
    """Single alert response."""
    event_id: str
    track_id: int
    risk_level: str
    risk_score: float
    message: str
    zone: str
    factors: List[str]
    timestamp: str
    acknowledged: bool


class AlertSummaryResponse(BaseModel):
    """Alert summary response."""
    total_alerts: int
    by_level: Dict[str, int]
    recent_alerts: List[Dict[str, Any]]
    start_time: Optional[str]
    end_time: Optional[str]


class AcknowledgeResponse(BaseModel):
    """Acknowledge response."""
    message: str
    event_id: str


def _persistence_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail="Durable alert persistence is unavailable. Alerts cannot be served from process memory.",
    )


@router.get("", response_model=List[Dict[str, Any]])
async def get_alerts(
    limit: int = Query(50, ge=1, le=500),
    level: Optional[str] = None,
    _: str = Depends(verify_api_key)
):
    """
    Get recent alerts.
    
    Args:
        limit: Maximum alerts to return
        level: Filter by level (INFO, WARNING, HIGH, CRITICAL)
    """
    manager = get_alert_manager()
    try:
        return manager.get_persisted_alerts(limit=limit, level=level)
    except Exception as exc:
        raise _persistence_unavailable(exc) from exc


@router.get("/active", response_model=List[Dict[str, Any]])
async def get_active_alerts(
    limit: int = Query(20, ge=1, le=100),
    _: str = Depends(verify_api_key)
):
    """
    Get unacknowledged alerts only.
    """
    manager = get_alert_manager()
    try:
        return manager.get_persisted_alerts(limit=limit, active_only=True)
    except Exception as exc:
        raise _persistence_unavailable(exc) from exc


@router.get("/summary", response_model=AlertSummaryResponse)
async def get_alert_summary(_: str = Depends(verify_api_key)):
    """
    Get alert summary statistics.
    """
    manager = get_alert_manager()
    try:
        summary = manager.get_persisted_summary()
        recent_alerts = manager.get_persisted_alerts(limit=10)
    except Exception as exc:
        raise _persistence_unavailable(exc) from exc
    return AlertSummaryResponse(
        total_alerts=summary["total_alerts"],
        by_level=summary["by_level"],
        recent_alerts=recent_alerts,
        start_time=None,
        end_time=None,
    )


@router.post("/{event_id}/acknowledge")
async def acknowledge_alert(
    event_id: str,
    x_aegis_actor: Optional[str] = Header(default=None),
    _: str = Depends(verify_api_key)
):
    """
    Acknowledge an alert.
    """
    manager = get_alert_manager()
    actor = str(x_aegis_actor or "").strip()[:160] or "api-key-operator"
    try:
        acknowledged = manager.acknowledge_persisted_alert(event_id, acknowledged_by=actor)
    except Exception as exc:
        raise _persistence_unavailable(exc) from exc
    if not acknowledged:
        raise HTTPException(status_code=404, detail=f"Alert {event_id} not found")
    from aegis.audit import record_audit

    record_audit(
        "alert.acknowledged",
        actor_id=actor,
        resource_type="alert",
        resource_id=event_id,
        details={"source": "operator_api"},
    )
    return {"message": "Alert acknowledged", "event_id": event_id}


@router.get("/queue", response_model=List[Dict[str, Any]])
async def get_alert_queue(
    limit: int = Query(20, ge=1, le=50),
    _: str = Depends(verify_api_key)
):
    """
    Get durable alerts currently queued for in-app delivery.
    """
    manager = get_alert_manager()
    try:
        return [
            alert for alert in manager.get_persisted_alerts(limit=limit * 5)
            if alert.get("delivery_status") == "queued"
        ][:limit]
    except Exception as exc:
        raise _persistence_unavailable(exc) from exc


@router.post("/clear")
async def clear_alerts(_: str = Depends(verify_api_key)):
    """
    Bulk deletion is intentionally unavailable for durable alert history.
    """
    raise HTTPException(
        status_code=409,
        detail="Durable alerts cannot be cleared in bulk. Acknowledge individual alerts instead.",
    )


@router.get("/count")
async def get_alert_count(_: str = Depends(verify_api_key)):
    """
    Get total alert count and breakdown.
    """
    manager = get_alert_manager()
    try:
        summary = manager.get_persisted_summary()
    except Exception as exc:
        raise _persistence_unavailable(exc) from exc
    return {
        "total": summary["total_alerts"],
        "by_level": summary["by_level"],
        "active": summary["active"],
    }
