"""
AegisAI - Smart City Risk Intelligence System
API Routes - Events Endpoint

GET /events - Recent risk events and alerts

Phase 4: Response & Productization Layer
"""

from typing import Optional
from fastapi import APIRouter, Query
from aegis.api.state import get_state

router = APIRouter(prefix="/events", tags=["events"])


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
    events = state.get_events(limit=limit)
    
    # Filter by level if specified
    if level:
        level_upper = level.upper()
        events = [e for e in events if e.get("risk_level") == level_upper]
    
    return {
        "count": len(events),
        "events": events
    }
