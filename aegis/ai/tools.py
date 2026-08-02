"""
AegisAI - AI Tools

Real backend tool functions that collect verified data from the system.
Gemini NEVER queries the database — these tools do it and pass the results.

Each tool returns a dict with real data from the running system.
"""

from __future__ import annotations

import logging
import os
import platform
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# System Health Tools
# ---------------------------------------------------------------------------

def get_system_health() -> Dict[str, Any]:
    """Get overall system health status."""
    result: Dict[str, Any] = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "platform": platform.system(),
    }

    # Database
    try:
        from aegis.database.connection import check_connection
        result["database"] = "connected" if check_connection() else "disconnected"
    except Exception:
        result["database"] = "unavailable"

    # Redis event bus
    try:
        from aegis.core.events import get_event_bus
        bus = get_event_bus()
        result["redis"] = "connected" if bus.is_connected else "in-memory"
    except Exception:
        result["redis"] = "unavailable"

    # Pipeline
    try:
        from aegis.pipeline.startup import get_pipeline
        pipeline = get_pipeline()
        result["pipeline"] = "running" if pipeline and pipeline._running else "stopped"
    except Exception:
        result["pipeline"] = "unavailable"

    # YOLO model
    try:
        from pathlib import Path
        model_path = Path("yolo11n.pt")
        if not model_path.exists():
            model_path = Path("yolov8n.pt")
        result["yolo_model"] = str(model_path.name) if model_path.exists() else "not_found"
    except Exception:
        result["yolo_model"] = "unknown"

    return result


def get_gpu_usage() -> Dict[str, Any]:
    """Get GPU utilization if available."""
    try:
        import torch
        if torch.cuda.is_available():
            return {
                "available": True,
                "device": torch.cuda.get_device_name(0),
                "memory_allocated_mb": round(torch.cuda.memory_allocated() / 1024 / 1024, 1),
                "memory_total_mb": round(torch.cuda.get_device_properties(0).total_mem / 1024 / 1024, 1),
            }
    except ImportError:
        pass
    return {"available": False, "message": "CUDA not available"}


def get_database_status() -> Dict[str, Any]:
    """Check database connectivity and basic stats."""
    try:
        from aegis.database.connection import check_connection, get_db_session
        connected = check_connection()
        if not connected:
            return {"status": "disconnected"}
        return {"status": "connected"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# Camera Tools
# ---------------------------------------------------------------------------

def get_camera_status() -> Dict[str, Any]:
    """Get status of all cameras."""
    try:
        from aegis.camera.registry import CameraRegistry
        registry = CameraRegistry()
        cameras = registry.list()
        online = [c for c in cameras if getattr(c, "status", "") == "online"]
        offline = [c for c in cameras if getattr(c, "status", "") != "online"]

        return {
            "total": len(cameras),
            "online": len(online),
            "offline": len(offline),
            "cameras": [
                {
                    "camera_id": getattr(c, "camera_id", "unknown"),
                    "name": getattr(c, "name", ""),
                    "status": getattr(c, "status", "unknown"),
                    "source_type": getattr(c, "source_type", "unknown"),
                }
                for c in cameras[:20]  # Limit to avoid huge payloads
            ],
        }
    except Exception as exc:
        logger.debug("Camera status unavailable: %s", exc)
        return {"total": 0, "online": 0, "offline": 0, "cameras": [], "error": str(exc)}


def get_camera_detail(camera_id: str) -> Dict[str, Any]:
    """Get detailed info for a specific camera."""
    try:
        from aegis.camera.registry import CameraRegistry
        registry = CameraRegistry()
        config = registry.get(camera_id)
        if config is None:
            return {"error": f"Camera {camera_id} not found"}
        return {
            "camera_id": config.camera_id,
            "name": getattr(config, "name", ""),
            "status": getattr(config, "status", "unknown"),
            "source_type": getattr(config, "source_type", ""),
            "url": getattr(config, "url", ""),
        }
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Events & Alerts Tools
# ---------------------------------------------------------------------------

def get_recent_events(limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent events from the database or event buffer."""
    try:
        from aegis.pipeline.startup import get_alerting_stage
        stage = get_alerting_stage()
        if stage:
            return stage.get_recent_events(limit=limit)
    except Exception:
        pass

    # Fallback: try database
    try:
        from aegis.database.connection import get_db_session
        from aegis.database.repositories import EventRepository
        # ``get_db_session`` is a context manager.  Passing it directly to a
        # repository leaves the repository with a context-manager object,
        # rather than an entered SQLAlchemy Session.
        with get_db_session() as session:
            events = EventRepository(session).get_recent(limit=limit)
            return [
                {
                    "id": str(e.id),
                    "event_id": str(e.id),
                    "type": e.event_type,
                    "event_type": e.event_type,
                    # Camera ID is retained in metadata by the active
                    # aegis.database persistence path; older records may only
                    # have the camera/zone field.
                    "camera_id": ((e.event_metadata or {}).get("camera_id") or e.zone),
                    "timestamp": (e.timestamp or e.created_at).isoformat() if (e.timestamp or e.created_at) else None,
                    "risk_level": e.risk_level,
                    "risk_score": e.risk_score,
                    "message": e.message,
                    "data": e.event_metadata or {},
                }
                for e in events
            ]
    except Exception as exc:
        logger.debug("Recent persisted events unavailable: %s", exc)
        return []


def get_active_alerts(limit: int = 10) -> List[Dict[str, Any]]:
    """Get active/recent alerts."""
    try:
        from aegis.pipeline.startup import get_alerting_stage
        stage = get_alerting_stage()
        if stage:
            events = stage.get_recent_events(limit=limit)
            return [e for e in events if e.get("type") == "risk_alert"]
    except Exception:
        pass
    return []


def get_high_risk_events(limit: int = 5) -> List[Dict[str, Any]]:
    """Get the highest risk events from today."""
    alerts = get_active_alerts(limit=20)
    sorted_alerts = sorted(alerts, key=lambda a: a.get("risk_score", 0), reverse=True)
    return sorted_alerts[:limit]


# ---------------------------------------------------------------------------
# Tracking Tools
# ---------------------------------------------------------------------------

def get_active_tracks() -> Dict[str, Any]:
    """Get current active tracking information."""
    try:
        from aegis.pipeline.startup import get_alerting_stage
        stage = get_alerting_stage()
        if stage:
            recent = stage.get_recent_detections(limit=5)
            total_tracks = sum(d.get("track_count", 0) for d in recent)
            return {
                "active_cameras_processing": len(set(d.get("camera_id") for d in recent)),
                "total_recent_tracks": total_tracks,
                "recent_detections": recent[:5],
            }
    except Exception:
        pass
    return {"active_cameras_processing": 0, "total_recent_tracks": 0, "recent_detections": []}


# ---------------------------------------------------------------------------
# Detection Statistics Tools
# ---------------------------------------------------------------------------

def get_detection_statistics() -> Dict[str, Any]:
    """Get detection statistics from the pipeline."""
    try:
        from aegis.pipeline.startup import get_pipeline
        pipeline = get_pipeline()
        if pipeline:
            stats = pipeline.get_stats()
            return {
                "pipeline_running": stats.get("running", False),
                "stages": stats.get("stages", []),
            }
    except Exception:
        pass
    return {"pipeline_running": False, "stages": []}


# ---------------------------------------------------------------------------
# Report Generation Tools
# ---------------------------------------------------------------------------

def generate_incident_report(incident_id: Optional[str] = None) -> Dict[str, Any]:
    """Generate an incident report from system data."""
    health = get_system_health()
    cameras = get_camera_status()
    events = get_recent_events(limit=20)
    alerts = get_active_alerts(limit=10)

    return {
        "report_type": "incident_summary",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "system_health": health,
        "cameras_summary": {
            "total": cameras.get("total", 0),
            "online": cameras.get("online", 0),
        },
        "events_count": len(events),
        "alerts_count": len(alerts),
        "high_risk_events": get_high_risk_events(limit=5),
        "incident_id": incident_id,
    }


# ---------------------------------------------------------------------------
# Search Tools
# ---------------------------------------------------------------------------

def search_semantic(query: str) -> Dict[str, Any]:
    """Perform semantic search across the system."""
    try:
        from aegis.api.state import get_state
        state = get_state()
        engine = getattr(state, "semantic_query_engine", None)
        if engine:
            results = engine.search(query)
            return {"query": query, "results": results, "count": len(results)}
    except Exception:
        pass
    return {"query": query, "results": [], "count": 0, "message": "Semantic search not available"}


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

TOOL_REGISTRY: Dict[str, callable] = {
    "get_system_health": get_system_health,
    "get_camera_status": get_camera_status,
    "get_camera_detail": get_camera_detail,
    "get_recent_events": get_recent_events,
    "get_active_alerts": get_active_alerts,
    "get_high_risk_events": get_high_risk_events,
    "get_active_tracks": get_active_tracks,
    "get_detection_statistics": get_detection_statistics,
    "get_gpu_usage": get_gpu_usage,
    "get_database_status": get_database_status,
    "generate_incident_report": generate_incident_report,
    "search_semantic": search_semantic,
}


def execute_tool(name: str, **kwargs) -> Any:
    """Execute a tool by name with arguments."""
    tool = TOOL_REGISTRY.get(name)
    if tool is None:
        return {"error": f"Unknown tool: {name}"}
    try:
        return tool(**kwargs)
    except Exception as exc:
        logger.error("Tool %s failed: %s", name, exc)
        return {"error": f"Tool {name} failed: {str(exc)}"}
