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

from aegis.intelligence.event_access import load_persisted_event_records, merge_event_records

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# System Health Tools
# ---------------------------------------------------------------------------

def get_system_health() -> Dict[str, Any]:
    """Get overall system health status."""
    result: Dict[str, Any] = {
        "availability": "available",
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

    critical = (result.get("database") == "connected" and result.get("pipeline") == "running")
    model_available = result.get("yolo_model") not in {"not_found", "unknown"}
    result["status"] = "healthy" if critical and model_available else "degraded"
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
        from aegis.api.routes.cameras import get_camera_manager

        cameras = get_camera_manager().list_cameras()
        online = [camera for camera in cameras if (camera.get("runtime") or {}).get("status") == "online" and (camera.get("runtime") or {}).get("running")]
        offline = [camera for camera in cameras if (camera.get("runtime") or {}).get("status") in {"offline", "error", "stopped"}]

        return {
            "availability": "available",
            "total": len(cameras),
            "online": len(online),
            "offline": len(offline),
            "cameras": [
                {
                    "camera_id": camera.get("camera_id"),
                    "name": camera.get("name") or "",
                    "status": (camera.get("runtime") or {}).get("status", "unknown"),
                    "source_type": camera.get("source_type", "unknown"),
                }
                for camera in cameras[:20]  # Limit to avoid huge payloads
            ],
        }
    except Exception as exc:
        logger.warning("Camera status unavailable: %s", type(exc).__name__)
        return {"availability": "unavailable", "reason": "Camera runtime status is unavailable."}


def get_camera_detail(camera_id: str) -> Dict[str, Any]:
    """Get detailed info for a specific camera."""
    try:
        from aegis.api.routes.cameras import get_camera_manager

        config = get_camera_manager().get_camera(camera_id)
        if config is None:
            return {"availability": "available", "error": f"Camera {camera_id} not found"}
        return {
            "availability": "available",
            "camera_id": config.get("camera_id"),
            "name": config.get("name") or "",
            "status": (config.get("runtime") or {}).get("status", "unknown"),
            "source_type": config.get("source_type", ""),
        }
    except Exception as exc:
        return {"availability": "unavailable", "reason": "Camera runtime status is unavailable."}


# ---------------------------------------------------------------------------
# Events & Alerts Tools
# ---------------------------------------------------------------------------

def get_recent_events(limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent events from the active runtime and durable evidence store."""
    bounded_limit = max(1, min(int(limit), 100))
    stage_events: List[Dict[str, Any]] = []
    try:
        from aegis.pipeline.startup import get_alerting_stage
        stage = get_alerting_stage()
        if stage:
            stage_events = stage.get_recent_events(limit=bounded_limit)
    except Exception:
        stage_events = []

    runtime_events: List[Dict[str, Any]] = []
    try:
        from aegis.api.state import get_state

        runtime_events = get_state().get_events(limit=bounded_limit)
    except Exception as exc:
        logger.debug("Runtime event state unavailable: %s", exc)

    try:
        durable_events = load_persisted_event_records(limit=bounded_limit)
    except Exception as exc:
        logger.debug("Recent persisted events unavailable: %s", exc)
        durable_events = []

    merged = merge_event_records(durable_events, stage_events, runtime_events, limit=bounded_limit)
    return [_event_projection(event) for event in merged]


def get_active_alerts(limit: int = 10) -> List[Dict[str, Any]]:
    """Get durable unacknowledged alert records, never inferred events."""
    bounded_limit = max(1, min(int(limit), 100))
    try:
        from aegis.database.connection import get_db_session
        from aegis.database.repositories import OperationalAlertRepository

        with get_db_session() as session:
            return [record.to_dict() for record in OperationalAlertRepository(session).get_active(bounded_limit)]
    except Exception as exc:
        logger.warning("Durable alerts unavailable: %s", type(exc).__name__)
        raise RuntimeError("Durable alert storage is unavailable.") from exc


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
        from aegis.api.state import get_state

        tracks = get_state().get_tracks()
        return {
            "availability": "available",
            "active_cameras_processing": len({track.get("camera_id") for track in tracks if track.get("camera_id")} ),
            "total_recent_tracks": len(tracks),
            "recent_detections": tracks[:5],
        }
    except Exception as exc:
        logger.warning("Active tracking unavailable: %s", type(exc).__name__)
        return {"availability": "unavailable", "reason": "Live tracking state is unavailable."}


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
                "availability": "available",
                "pipeline_running": stats.get("running", False),
                "stages": stats.get("stages", []),
            }
    except Exception as exc:
        logger.warning("Pipeline statistics unavailable: %s", type(exc).__name__)
        return {"availability": "unavailable", "reason": "Pipeline statistics are unavailable."}
    return {"availability": "unavailable", "reason": "Pipeline is not initialized."}


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
            "availability": cameras.get("availability", "unavailable"),
            "total": cameras.get("total"),
            "online": cameras.get("online"),
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
            try:
                durable_events = load_persisted_event_records(limit=100)
            except Exception as exc:
                return {
                    "query": query,
                    "availability": "unavailable",
                    "reason": "Durable evidence storage is unavailable.",
                    "results": [],
                    "count": 0,
                }
            execution = engine.search(
                prompt=query,
                tracks=state.get_tracks(),
                events=merge_event_records(durable_events, state.get_events(limit=100)),
                statistics=state.get_statistics(),
            )
            return {"query": query, "availability": "available", "results": execution.results, "count": len(execution.results)}
    except Exception as exc:
        logger.debug("Semantic search unavailable: %s", exc)
    return {"query": query, "availability": "unavailable", "reason": "Semantic search is not available.", "results": [], "count": 0}


def _event_projection(event: Dict[str, Any]) -> Dict[str, Any]:
    """Keep the legacy tool response stable while sourcing unified events."""
    event_id = str(event.get("event_id") or event.get("id") or "")
    return {
        "id": str(event.get("id") or event_id),
        "event_id": event_id,
        "type": event.get("type") or event.get("event_type"),
        "event_type": event.get("event_type") or event.get("type"),
        "camera_id": event.get("camera_id") or event.get("zone"),
        "timestamp": event.get("timestamp"),
        "risk_level": event.get("risk_level") or event.get("severity"),
        "risk_score": event.get("risk_score"),
        "message": event.get("message") or event.get("explanation") or event.get("description") or "",
        "data": event.get("data") if isinstance(event.get("data"), dict) else {},
    }


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
