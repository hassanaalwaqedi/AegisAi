"""
AegisAI - Camera Management API Routes

REST endpoints for camera management and health monitoring.

Copyright 2024 AegisAI Project
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from aegis.api.security import verify_api_key

router = APIRouter(prefix="/cameras", tags=["cameras"])


# Global camera manager reference - set by app on startup
_camera_manager = None


def get_camera_manager():
    """Get the global camera manager instance."""
    global _camera_manager
    if _camera_manager is None:
        # Create on demand if not set
        from aegis.video.camera_manager import CameraManager
        _camera_manager = CameraManager()
    return _camera_manager


def set_camera_manager(manager):
    """Set the global camera manager instance."""
    global _camera_manager
    _camera_manager = manager


class AddCameraRequest(BaseModel):
    """Request to add a new camera."""
    camera_id: str
    url: str
    name: Optional[str] = None
    location: Optional[str] = None
    enabled: bool = True
    auto_start: bool = True
    connection_timeout: float = 5.0
    max_retries: int = 10


class CameraResponse(BaseModel):
    """Camera information response."""
    camera_id: str
    name: Optional[str]
    location: Optional[str]
    enabled: bool
    health: str


class CameraStatsResponse(BaseModel):
    """Camera statistics response."""
    camera_id: str
    health: str
    fps: float
    latency_ms: float
    frames_received: int
    frames_dropped: int
    reconnect_count: int
    error_message: Optional[str]


class HealthSummaryResponse(BaseModel):
    """Aggregated health summary."""
    total_cameras: int
    cameras_up: int
    cameras_degraded: int
    cameras_down: int
    overall_health: str
    total_fps: float


@router.get("", response_model=List[CameraResponse])
async def list_cameras(_: str = Depends(verify_api_key)):
    """
    List all configured cameras.
    
    Returns all cameras with their current health status.
    """
    manager = get_camera_manager()
    cameras = manager.list_cameras()
    
    return [CameraResponse(**cam) for cam in cameras]


@router.get("/health", response_model=HealthSummaryResponse)
async def get_health_summary(_: str = Depends(verify_api_key)):
    """
    Get aggregated health summary for all cameras.
    
    Returns overall system health and per-camera status.
    """
    manager = get_camera_manager()
    return manager.get_health_summary()


@router.get("/{camera_id}", response_model=CameraStatsResponse)
async def get_camera_stats(camera_id: str, _: str = Depends(verify_api_key)):
    """
    Get detailed statistics for a specific camera.
    
    Args:
        camera_id: Camera identifier
    """
    manager = get_camera_manager()
    stats = manager.get_camera_stats(camera_id)
    
    if stats is None:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found")
    
    return CameraStatsResponse(
        camera_id=camera_id,
        health=stats.health.value,
        fps=stats.fps,
        latency_ms=stats.latency_ms,
        frames_received=stats.frames_received,
        frames_dropped=stats.frames_dropped,
        reconnect_count=stats.reconnect_count,
        error_message=stats.error_message,
    )


@router.post("", response_model=CameraResponse)
async def add_camera(
    request: AddCameraRequest,
    _: str = Depends(verify_api_key)
):
    """
    Add a new camera to the system.
    
    The camera will start streaming automatically if auto_start is True.
    """
    manager = get_camera_manager()
    
    success = manager.add_camera(
        camera_id=request.camera_id,
        url=request.url,
        name=request.name,
        location=request.location,
        enabled=request.enabled,
        auto_start=request.auto_start,
        connection_timeout=request.connection_timeout,
        max_retries=request.max_retries,
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Failed to add camera. ID may already exist or max cameras reached.")
    
    return CameraResponse(
        camera_id=request.camera_id,
        name=request.name,
        location=request.location,
        enabled=request.enabled,
        health="unknown",
    )


@router.delete("/{camera_id}")
async def remove_camera(camera_id: str, _: str = Depends(verify_api_key)):
    """
    Remove a camera from the system.
    
    This will stop the camera stream and remove all associated data.
    """
    manager = get_camera_manager()
    
    success = manager.remove_camera(camera_id)
    
    if not success:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found")
    
    return {"message": f"Camera {camera_id} removed"}


@router.post("/{camera_id}/start")
async def start_camera(camera_id: str, _: str = Depends(verify_api_key)):
    """Start a specific camera stream."""
    manager = get_camera_manager()
    
    success = manager.start_camera(camera_id)
    
    if not success:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found")
    
    return {"message": f"Camera {camera_id} started"}


@router.post("/{camera_id}/stop")
async def stop_camera(camera_id: str, _: str = Depends(verify_api_key)):
    """Stop a specific camera stream."""
    manager = get_camera_manager()
    
    success = manager.stop_camera(camera_id)
    
    if not success:
        raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found")
    
    return {"message": f"Camera {camera_id} stopped"}


@router.get("/{camera_id}/events", response_model=List[Dict[str, Any]])
async def get_camera_events(
    camera_id: str,
    limit: int = 50,
    event_type: Optional[str] = None,
    _: str = Depends(verify_api_key)
):
    """
    Get recent events from a camera.
    
    Args:
        camera_id: Camera identifier
        limit: Maximum events to return
        event_type: Filter by event type (health_change, detection, alert)
    """
    manager = get_camera_manager()
    
    # Filter events for this camera
    all_events = manager.get_recent_events(limit=limit * 2, event_type=event_type)
    camera_events = [e for e in all_events if e.get("camera_id") == camera_id]
    
    return camera_events[:limit]
