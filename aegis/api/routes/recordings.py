"""
AegisAI - Recordings API Routes

REST endpoints for accessing recorded risk events.

Copyright 2024 AegisAI Project
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Query, Response
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from aegis.api.security import verify_api_key
from aegis.recording.models import RecordingMetadata, RecordingEvent

router = APIRouter(prefix="/recordings", tags=["recordings"])

# Global metadata instance
_metadata: Optional[RecordingMetadata] = None


def get_metadata() -> RecordingMetadata:
    """Get global metadata storage instance."""
    global _metadata
    if _metadata is None:
        _metadata = RecordingMetadata()
    return _metadata


def set_metadata(metadata: RecordingMetadata) -> None:
    """Set global metadata instance."""
    global _metadata
    _metadata = metadata


class RecordingResponse(BaseModel):
    """Single recording event response."""
    event_id: str
    camera_id: str
    start_time: str
    end_time: Optional[str]
    max_risk_score: float
    detected_object_types: List[str]
    file_path: str
    duration_seconds: float
    trigger_risk_score: float


class RecordingsListResponse(BaseModel):
    """List of recordings response."""
    total: int
    recordings: List[Dict[str, Any]]


class RecordingStatsResponse(BaseModel):
    """Recording statistics response."""
    total_recordings: int
    total_duration_seconds: float
    cameras_with_recordings: int
    risk_distribution: Dict[str, int]


@router.get("", response_model=RecordingsListResponse)
async def list_recordings(
    camera_id: Optional[str] = Query(None, description="Filter by camera ID"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    min_risk: float = Query(0.0, ge=0.0, le=1.0, description="Minimum risk score"),
    limit: int = Query(50, ge=1, le=500, description="Maximum results"),
    _: str = Depends(verify_api_key)
):
    """
    List recorded risk events with filtering.
    
    Args:
        camera_id: Filter by specific camera
        start_date: Filter by start date (inclusive)
        end_date: Filter by end date (inclusive)
        min_risk: Minimum risk score threshold
        limit: Maximum number of results
    """
    metadata = get_metadata()
    
    # Parse dates
    parsed_start = None
    parsed_end = None
    
    if start_date:
        try:
            parsed_start = datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format")
    
    if end_date:
        try:
            parsed_end = datetime.strptime(end_date, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format")
    
    # Get filtered events
    events = metadata.list_events(
        camera_id=camera_id,
        start_date=parsed_start,
        end_date=parsed_end,
        min_risk=min_risk,
        limit=limit
    )
    
    return RecordingsListResponse(
        total=len(events),
        recordings=[e.to_dict() for e in events]
    )


@router.get("/stats", response_model=RecordingStatsResponse)
async def get_recording_stats(_: str = Depends(verify_api_key)):
    """Get recording statistics."""
    metadata = get_metadata()
    events = metadata.list_events(limit=1000)
    
    # Calculate stats
    total_duration = sum(e.duration_seconds for e in events)
    cameras = set(e.camera_id for e in events)
    
    # Risk distribution
    risk_dist = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for e in events:
        if e.max_risk_score >= 0.8:
            risk_dist["critical"] += 1
        elif e.max_risk_score >= 0.6:
            risk_dist["high"] += 1
        elif e.max_risk_score >= 0.4:
            risk_dist["medium"] += 1
        else:
            risk_dist["low"] += 1
    
    return RecordingStatsResponse(
        total_recordings=len(events),
        total_duration_seconds=total_duration,
        cameras_with_recordings=len(cameras),
        risk_distribution=risk_dist
    )


@router.get("/{event_id}", response_model=Dict[str, Any])
async def get_recording(
    event_id: str,
    _: str = Depends(verify_api_key)
):
    """
    Get details of a specific recording event.
    """
    metadata = get_metadata()
    event = metadata.get(event_id)
    
    if not event:
        raise HTTPException(status_code=404, detail=f"Recording {event_id} not found")
    
    # Check if file exists
    file_exists = Path(event.file_path).exists() if event.file_path else False
    
    result = event.to_dict()
    result["file_exists"] = file_exists
    
    return result


@router.get("/{event_id}/stream")
async def stream_recording(
    event_id: str,
    _: str = Depends(verify_api_key)
):
    """
    Stream recording video file.
    
    Supports HTTP Range requests for seeking.
    """
    metadata = get_metadata()
    event = metadata.get(event_id)
    
    if not event:
        raise HTTPException(status_code=404, detail=f"Recording {event_id} not found")
    
    file_path = Path(event.file_path)
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Recording file not found")
    
    # Return file with Range support
    return FileResponse(
        path=str(file_path),
        media_type="video/mp4",
        filename=f"{event_id}.mp4"
    )


@router.get("/{event_id}/download")
async def download_recording(
    event_id: str,
    _: str = Depends(verify_api_key)
):
    """
    Download recording as file attachment.
    """
    metadata = get_metadata()
    event = metadata.get(event_id)
    
    if not event:
        raise HTTPException(status_code=404, detail=f"Recording {event_id} not found")
    
    file_path = Path(event.file_path)
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Recording file not found")
    
    return FileResponse(
        path=str(file_path),
        media_type="video/mp4",
        filename=f"{event.camera_id}_{event_id}.mp4",
        headers={"Content-Disposition": f"attachment; filename={event.camera_id}_{event_id}.mp4"}
    )


@router.delete("/{event_id}")
async def delete_recording(
    event_id: str,
    delete_file: bool = Query(True, description="Also delete video file"),
    _: str = Depends(verify_api_key)
):
    """
    Delete a recording event and optionally its file.
    """
    metadata = get_metadata()
    event = metadata.get(event_id)
    
    if not event:
        raise HTTPException(status_code=404, detail=f"Recording {event_id} not found")
    
    # Delete file if requested
    if delete_file and event.file_path:
        file_path = Path(event.file_path)
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to delete file: {e}")
    
    # Delete metadata
    metadata.delete(event_id)
    
    return {"message": f"Recording {event_id} deleted", "file_deleted": delete_file}


@router.get("/cameras/list")
async def list_cameras_with_recordings(_: str = Depends(verify_api_key)):
    """Get list of cameras that have recordings."""
    metadata = get_metadata()
    events = metadata.list_events(limit=1000)
    
    cameras = {}
    for e in events:
        if e.camera_id not in cameras:
            cameras[e.camera_id] = {
                "camera_id": e.camera_id,
                "recording_count": 0,
                "total_duration": 0.0,
                "latest_recording": None,
            }
        cameras[e.camera_id]["recording_count"] += 1
        cameras[e.camera_id]["total_duration"] += e.duration_seconds
        
        if cameras[e.camera_id]["latest_recording"] is None:
            cameras[e.camera_id]["latest_recording"] = e.start_time.isoformat()
    
    return {"cameras": list(cameras.values())}
