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
    events = state.get_events(limit=1000)
    registry = state.get_object_registry()
    alerts_by_severity = {"LOW": 0, "CANDIDATE_MEDIUM": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
    events_by_type = {}
    for event in events:
        level = event.get("risk_level") or event.get("severity")
        if level in alerts_by_severity:
            alerts_by_severity[level] += 1
        event_type = str(event.get("event_type") or "event")
        events_by_type[event_type] = events_by_type.get(event_type, 0) + 1
    
    return {
        "crowd": {
            "person_count": stats.get("person_count", 0),
            "vehicle_count": stats.get("vehicle_count", 0),
            "weapon_count": stats.get("weapon_count", 0),
            "crowd_detected": stats.get("crowd_detected", False),
            "max_density": stats.get("max_density", 0)
        },
        "detections": {
            "active_count": stats.get("active_detections_count", 0),
            "people_count": stats.get("person_count", 0),
            "vehicles_count": stats.get("vehicle_count", 0),
            "weapons_count": stats.get("weapon_count", 0),
            "by_class": stats.get("detections_by_class", {}),
            "object_registry_count": len(registry),
            "weapon_associations_count": stats.get("association_count", 0),
            "critical_associations_count": stats.get("critical_association_count", 0),
        },
        "risk": {
            "distribution": stats.get("risk_distribution", {
                "LOW": 0, "CANDIDATE_MEDIUM": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0
            }),
            "max_level": status.get("max_risk_level", "LOW"),
            "max_score": status.get("max_risk_score", 0.0)
        },
        "processing": {
            "frames": status.get("frames_processed", 0),
            "fps": status.get("current_fps", 0.0),
            "active_tracks": status.get("active_tracks", 0)
        },
        "alerts_by_severity": alerts_by_severity,
        "events_by_type": events_by_type,
        "latest_detection_events": events[-20:],
        "object_registry": registry,
        "model": {
            "model_name": status.get("model_name", ""),
            "supported_classes": status.get("supported_classes", []),
            "weapon_detection_supported": status.get("weapon_detection_supported", False),
            "person_detector": status.get("person_detector", {}),
            "weapon_detector": status.get("weapon_detector", {}),
            "action_recognition_supported": status.get("action_recognition_supported", False),
            "pose_estimation_supported": status.get("pose_estimation_supported", False),
            "semantic_verification_supported": status.get("semantic_verification_supported", False),
        }
    }
