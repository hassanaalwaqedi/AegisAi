"""
AegisAI - Alert API Routes

REST endpoints for alert management and acknowledgment.

Copyright 2024 AegisAI Project
"""

from fastapi import APIRouter, HTTPException, Depends, Query
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
    alerts = manager.get_recent_alerts(count=limit)
    
    result = [a.to_dict() for a in alerts]
    
    if level:
        result = [a for a in result if a.get('risk_level') == level.upper()]
    
    return result


@router.get("/active", response_model=List[Dict[str, Any]])
async def get_active_alerts(
    limit: int = Query(20, ge=1, le=100),
    _: str = Depends(verify_api_key)
):
    """
    Get unacknowledged alerts only.
    """
    manager = get_alert_manager()
    alerts = manager.get_recent_alerts(count=limit * 2)
    
    active = [a.to_dict() for a in alerts if not a.acknowledged]
    return active[:limit]


@router.get("/summary", response_model=AlertSummaryResponse)
async def get_alert_summary(_: str = Depends(verify_api_key)):
    """
    Get alert summary statistics.
    """
    manager = get_alert_manager()
    summary = manager.get_summary()
    
    return AlertSummaryResponse(
        total_alerts=summary.total_alerts,
        by_level=summary.by_level,
        recent_alerts=[a.to_dict() for a in summary.recent_alerts],
        start_time=summary.start_time.isoformat() if summary.start_time else None,
        end_time=summary.end_time.isoformat() if summary.end_time else None,
    )


@router.post("/{event_id}/acknowledge")
async def acknowledge_alert(
    event_id: str,
    _: str = Depends(verify_api_key)
):
    """
    Acknowledge an alert.
    """
    manager = get_alert_manager()
    alerts = manager.get_recent_alerts(count=500)
    
    for alert in alerts:
        if alert.event_id == event_id:
            alert.acknowledged = True
            return {"message": "Alert acknowledged", "event_id": event_id}
    
    raise HTTPException(status_code=404, detail=f"Alert {event_id} not found")


@router.get("/queue", response_model=List[Dict[str, Any]])
async def get_alert_queue(
    limit: int = Query(20, ge=1, le=50),
    _: str = Depends(verify_api_key)
):
    """
    Get alerts from the API queue (consumes them).
    
    Use this for real-time polling. Alerts are removed from queue after fetching.
    """
    manager = get_alert_manager()
    return manager.get_alerts_for_api(limit=limit)


@router.post("/clear")
async def clear_alerts(_: str = Depends(verify_api_key)):
    """
    Clear all alerts and reset manager.
    """
    manager = get_alert_manager()
    manager.reset()
    return {"message": "Alerts cleared"}


@router.get("/count")
async def get_alert_count(_: str = Depends(verify_api_key)):
    """
    Get total alert count and breakdown.
    """
    manager = get_alert_manager()
    summary = manager.get_summary()
    
    return {
        "total": summary.total_alerts,
        "by_level": summary.by_level,
        "active": sum(1 for a in manager.get_recent_alerts(100) if not a.acknowledged),
    }
