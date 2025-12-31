"""
AegisAI - Detection API Routes

REST endpoints for accessing AI detection results.

Copyright 2024 AegisAI Project
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from aegis.api.security import verify_api_key

router = APIRouter(prefix="/detections", tags=["detections"])


# Global pipeline reference - set by app on startup
_ai_pipeline = None


def get_ai_pipeline():
    """Get the global AI pipeline instance."""
    global _ai_pipeline
    return _ai_pipeline


def set_ai_pipeline(pipeline):
    """Set the global AI pipeline instance."""
    global _ai_pipeline
    _ai_pipeline = pipeline


class DetectionResponse(BaseModel):
    """Single detection response."""
    camera_id: str
    track_id: Optional[int]
    class_name: str
    class_id: int
    confidence: float
    bbox: List[int]
    risk_level: str
    risk_score: float
    timestamp: str
    frame_id: int


class AggregatedStatsResponse(BaseModel):
    """Aggregated detection statistics."""
    cameras_processing: int
    total_detections: int
    total_persons: int
    total_vehicles: int
    max_risk_level: str
    max_risk_score: float
    buffer_size: int
    running: bool


class CameraStatsResponse(BaseModel):
    """Per-camera detection statistics."""
    camera_id: str
    total_detections: int
    persons_detected: int
    vehicles_detected: int
    max_risk_level: str
    max_risk_score: float
    last_detection_time: Optional[str]
    fps: float


@router.get("", response_model=List[Dict[str, Any]])
async def get_detections(
    limit: int = Query(100, ge=1, le=1000),
    camera_id: Optional[str] = None,
    class_name: Optional[str] = None,
    min_risk: Optional[float] = Query(None, ge=0.0, le=1.0),
    _: str = Depends(verify_api_key)
):
    """
    Get recent detections with optional filters.
    
    Args:
        limit: Maximum detections to return (1-1000)
        camera_id: Filter by camera ID
        class_name: Filter by class (person, car, truck, etc.)
        min_risk: Minimum risk score filter (0.0-1.0)
    """
    pipeline = get_ai_pipeline()
    
    if pipeline is None:
        # Return empty if pipeline not running
        return []
    
    return pipeline.get_recent_detections(
        limit=limit,
        camera_id=camera_id,
        class_name=class_name,
        min_risk_score=min_risk,
    )


@router.get("/stats", response_model=AggregatedStatsResponse)
async def get_aggregated_stats(_: str = Depends(verify_api_key)):
    """
    Get aggregated detection statistics across all cameras.
    """
    pipeline = get_ai_pipeline()
    
    if pipeline is None:
        return AggregatedStatsResponse(
            cameras_processing=0,
            total_detections=0,
            total_persons=0,
            total_vehicles=0,
            max_risk_level="LOW",
            max_risk_score=0.0,
            buffer_size=0,
            running=False,
        )
    
    stats = pipeline.get_aggregated_stats()
    return AggregatedStatsResponse(**stats)


@router.get("/cameras", response_model=Dict[str, CameraStatsResponse])
async def get_per_camera_stats(_: str = Depends(verify_api_key)):
    """
    Get detection statistics for each camera.
    """
    pipeline = get_ai_pipeline()
    
    if pipeline is None:
        return {}
    
    return pipeline.get_camera_stats()


@router.get("/cameras/{camera_id}", response_model=List[Dict[str, Any]])
async def get_camera_detections(
    camera_id: str,
    limit: int = Query(50, ge=1, le=500),
    _: str = Depends(verify_api_key)
):
    """
    Get recent detections from a specific camera.
    """
    pipeline = get_ai_pipeline()
    
    if pipeline is None:
        return []
    
    return pipeline.get_recent_detections(limit=limit, camera_id=camera_id)


@router.post("/clear")
async def clear_detections(_: str = Depends(verify_api_key)):
    """
    Clear all stored detections and statistics.
    """
    pipeline = get_ai_pipeline()
    
    if pipeline is None:
        raise HTTPException(status_code=503, detail="AI pipeline not running")
    
    pipeline.clear_stats()
    return {"message": "Detections cleared"}


@router.get("/high-risk", response_model=List[Dict[str, Any]])
async def get_high_risk_detections(
    limit: int = Query(50, ge=1, le=200),
    threshold: float = Query(0.6, ge=0.0, le=1.0),
    _: str = Depends(verify_api_key)
):
    """
    Get recent high-risk detections.
    
    Args:
        limit: Maximum detections to return
        threshold: Minimum risk score (default 0.6 = HIGH)
    """
    pipeline = get_ai_pipeline()
    
    if pipeline is None:
        return []
    
    return pipeline.get_recent_detections(limit=limit, min_risk_score=threshold)
