"""
AegisAI - Smart City Risk Intelligence System
API Routes - Tracks Endpoint

GET /tracks - Active tracks with risk information

Phase 4: Response & Productization Layer
"""

from typing import Optional
from fastapi import APIRouter, Query
from aegis.api.state import get_state

router = APIRouter(prefix="/tracks", tags=["tracks"])


@router.get("")
async def get_tracks(
    min_risk: Optional[str] = Query(
        default=None, 
        description="Minimum risk level filter (LOW, MEDIUM, HIGH, CRITICAL)"
    )
):
    """
    Get active tracks with risk information.
    
    Args:
        min_risk: Filter by minimum risk level
    
    Returns:
        List of active tracks sorted by risk score
    """
    state = get_state()
    tracks = state.get_tracks(min_risk_level=min_risk)
    
    return {
        "count": len(tracks),
        "tracks": tracks
    }


@router.get("/concerning")
async def get_concerning_tracks():
    """
    Get only HIGH and CRITICAL risk tracks.
    
    Returns:
        List of concerning tracks
    """
    state = get_state()
    tracks = state.get_tracks(min_risk_level="HIGH")
    
    return {
        "count": len(tracks),
        "tracks": tracks
    }
