"""
AegisAI - Smart City Risk Intelligence System
API Routes - Statistics Endpoint

GET /statistics - Crowd and risk statistics

Phase 4: Response & Productization Layer
"""

from fastapi import APIRouter
from aegis.api.state import get_state

router = APIRouter(prefix="/statistics", tags=["statistics"])


@router.get("")
async def get_statistics():
    """
    Get crowd and risk statistics.
    
    Returns:
        Current statistics including crowd metrics and risk distribution
    """
    state = get_state()
    stats = state.get_statistics()
    status = state.get_status()
    
    return {
        "crowd": {
            "person_count": stats.get("person_count", 0),
            "vehicle_count": stats.get("vehicle_count", 0),
            "crowd_detected": stats.get("crowd_detected", False),
            "max_density": stats.get("max_density", 0)
        },
        "risk": {
            "distribution": stats.get("risk_distribution", {
                "LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0
            }),
            "max_level": status.get("max_risk_level", "LOW"),
            "max_score": status.get("max_risk_score", 0.0)
        },
        "processing": {
            "frames": status.get("frames_processed", 0),
            "fps": status.get("current_fps", 0.0),
            "active_tracks": status.get("active_tracks", 0)
        }
    }
