"""
AegisAI - Operations API Routes

API endpoints for restaurant/retail operations mode.

Endpoints:
- GET /operations/staff - Staff positions and coverage
- GET /operations/queue - Queue status
- GET /operations/kpi - Service KPIs
- GET /operations/safety - Safety alerts

Copyright 2024 AegisAI Project
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from aegis.core.mode_manager import get_current_mode, SystemMode, is_restaurant_mode
from aegis.api.security import verify_api_key

router = APIRouter(prefix="/operations", tags=["operations"])


def require_restaurant_mode():
    """Dependency that checks if in restaurant mode."""
    if not is_restaurant_mode():
        raise HTTPException(
            status_code=403,
            detail="Operations endpoints only available in RESTAURANT mode"
        )
    return True


# ============== Staff Endpoints ==============

class StaffMember(BaseModel):
    """Staff member position data."""
    track_id: int
    position: List[int]
    zone_id: Optional[str]
    idle_time_seconds: float
    is_idle: bool


class StaffResponse(BaseModel):
    """Staff overview response."""
    total_staff: int
    active_staff: int
    idle_staff: int
    staff: List[StaffMember]
    coverage: List[Dict[str, Any]]


@router.get("/staff", response_model=StaffResponse, dependencies=[Depends(require_restaurant_mode)])
async def get_staff_status():
    """
    Get current staff positions and coverage status.
    
    Returns:
        Staff positions, idle status, and zone coverage
    """
    # Import here to avoid circular imports and only load in restaurant mode
    try:
        from aegis.operations.employee_monitor import EmployeeMonitor
        # In real implementation, get from state manager
        # For now return empty/demo data
        return StaffResponse(
            total_staff=0,
            active_staff=0,
            idle_staff=0,
            staff=[],
            coverage=[]
        )
    except ImportError:
        raise HTTPException(status_code=500, detail="Employee monitor not available")


@router.get("/staff/heatmap")
async def get_staff_heatmap(
    grid_size: int = Query(50, ge=10, le=200),
    _: bool = Depends(require_restaurant_mode)
):
    """
    Get staff movement heatmap data.
    
    Args:
        grid_size: Grid cell size in pixels
        
    Returns:
        Heatmap grid data
    """
    return {
        "grid_size": grid_size,
        "cells": []  # Will be populated by actual implementation
    }


# ============== Queue Endpoints ==============

class QueueInfo(BaseModel):
    """Queue status information."""
    zone_id: str
    zone_name: str
    current_length: int
    avg_wait_minutes: float
    estimated_wait_minutes: float
    is_busy: bool


class QueuesResponse(BaseModel):
    """All queues response."""
    total_waiting: int
    queues: List[QueueInfo]


@router.get("/queue", response_model=QueuesResponse, dependencies=[Depends(require_restaurant_mode)])
async def get_queue_status():
    """
    Get status of all queues.
    
    Returns:
        Queue lengths, wait times, and busy status
    """
    return QueuesResponse(
        total_waiting=0,
        queues=[]
    )


@router.get("/queue/{zone_id}")
async def get_queue_detail(
    zone_id: str,
    _: bool = Depends(require_restaurant_mode)
):
    """
    Get detailed status of a specific queue.
    
    Args:
        zone_id: Queue zone identifier
        
    Returns:
        Detailed queue information
    """
    return {
        "zone_id": zone_id,
        "current_length": 0,
        "members": [],
        "avg_wait_seconds": 0,
        "service_rate_per_hour": 0
    }


# ============== KPI Endpoints ==============

class KPIResponse(BaseModel):
    """Service KPI metrics."""
    avg_service_time_minutes: float
    avg_turnover_per_hour: float
    total_customers_served: int
    current_occupancy_percent: float
    staff_efficiency_score: float
    busiest_hour: int


@router.get("/kpi", response_model=KPIResponse, dependencies=[Depends(require_restaurant_mode)])
async def get_kpis():
    """
    Get service key performance indicators.
    
    Returns:
        KPI metrics for the current session
    """
    return KPIResponse(
        avg_service_time_minutes=0,
        avg_turnover_per_hour=0,
        total_customers_served=0,
        current_occupancy_percent=0,
        staff_efficiency_score=50.0,
        busiest_hour=12
    )


@router.get("/kpi/history")
async def get_kpi_history(
    hours: int = Query(24, ge=1, le=168),
    _: bool = Depends(require_restaurant_mode)
):
    """
    Get historical KPI data.
    
    Args:
        hours: Number of hours of history
        
    Returns:
        Hourly KPI data
    """
    return {
        "hours_requested": hours,
        "data": []  # Hourly breakdown
    }


# ============== Safety Endpoints ==============

class SafetyAlert(BaseModel):
    """Safety alert information."""
    alert_id: str
    zone_name: str
    severity: str
    message: str
    timestamp: str
    acknowledged: bool


class SafetyResponse(BaseModel):
    """Safety alerts response."""
    total_alerts: int
    unacknowledged: int
    alerts: List[SafetyAlert]


@router.get("/safety", response_model=SafetyResponse, dependencies=[Depends(require_restaurant_mode)])
async def get_safety_alerts():
    """
    Get recent safety alerts.
    
    Returns:
        Safety alerts from the last hour
    """
    return SafetyResponse(
        total_alerts=0,
        unacknowledged=0,
        alerts=[]
    )


@router.post("/safety/{alert_id}/acknowledge", dependencies=[Depends(verify_api_key), Depends(require_restaurant_mode)])
async def acknowledge_alert(alert_id: str):
    """
    Acknowledge a safety alert.
    
    Args:
        alert_id: Alert to acknowledge
        
    Returns:
        Success status
    """
    return {"acknowledged": True, "alert_id": alert_id}


# ============== Combined Metrics ==============

@router.get("/metrics")
async def get_all_metrics():
    """
    Get combined operations metrics.
    Works in any mode - returns empty/demo data if not in restaurant mode.
    
    Returns:
        All operations metrics in one response
    """
    from datetime import datetime
    
    # Check if in restaurant mode for full data
    in_restaurant = is_restaurant_mode()
    
    return {
        "mode": "restaurant" if in_restaurant else "city",
        "staff": {
            "total": 0,
            "active": 0,
            "idle": 0
        },
        "queues": {
            "total_waiting": 0,
            "avg_wait_minutes": 0.0
        },
        "kpi": {
            "customers_served": 0,
            "efficiency_score": 50.0 if in_restaurant else 0.0
        },
        "safety": {
            "alerts_today": 0,
            "unacknowledged": 0
        },
        "timestamp": datetime.utcnow().isoformat()
    }
