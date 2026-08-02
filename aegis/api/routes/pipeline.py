"""
AegisAI - Pipeline API Routes

Monitoring and control endpoints for the AI processing pipeline.
Provides stats, stream info, and pipeline lifecycle management.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from aegis.api.security import verify_api_key

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.get("/stats")
async def get_pipeline_stats(_: bool = Depends(verify_api_key)) -> Dict[str, Any]:
    """Return stats for all pipeline stages."""
    try:
        from aegis.pipeline.startup import get_pipeline
        pipeline = get_pipeline()
        if pipeline is None:
            return {"status": "not_started", "stages": []}
        return {"status": "ok", **pipeline.get_stats()}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@router.get("/events/health")
async def get_event_bus_health(_: bool = Depends(verify_api_key)) -> Dict[str, Any]:
    """Return event bus (Redis) health status."""
    try:
        from aegis.core.events import get_event_bus
        bus = get_event_bus()
        health = bus.health_check()

        # Add stream info for key streams
        streams = {}
        for stream_name in ["frames", "detections", "tracks", "risks", "events"]:
            try:
                streams[stream_name] = bus.stream_info(stream_name)
            except Exception:
                streams[stream_name] = {"error": "unavailable"}

        return {
            "status": "ok",
            "redis": health,
            "streams": streams,
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@router.get("/events/streams/{stream_name}")
async def get_stream_info(
    stream_name: str, _: bool = Depends(verify_api_key)
) -> Dict[str, Any]:
    """Return detailed info about a specific stream."""
    try:
        from aegis.core.events import get_event_bus
        return get_event_bus().stream_info(stream_name)
    except Exception as exc:
        return {"error": str(exc)}
