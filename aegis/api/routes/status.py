"""
AegisAI - Smart City Risk Intelligence System
API Routes - Status & System Information

GET /status - System health, performance, and version info
GET /status/health - Simple health check
GET /status/version - Version and build info

Phase 4: Response & Productization Layer
"""

import os
import time
import platform
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from aegis.api.state import get_state

router = APIRouter(prefix="/status", tags=["status"])

# Application metadata
APP_VERSION = "5.0.0"
APP_NAME = "AegisAI"
BUILD_DATE = "2024-12-30"


class SystemStatus(BaseModel):
    """System status response model."""
    status: str
    version: str
    uptime_seconds: float
    fps: float
    frames_processed: int
    active_tracks: int
    total_alerts: int
    high_risk_count: int
    semantic_enabled: bool


class VersionInfo(BaseModel):
    """Version information response model."""
    name: str
    version: str
    build_date: str
    python_version: str
    platform: str
    phases: dict


class PerformanceMetrics(BaseModel):
    """Performance metrics response model."""
    fps: float
    avg_inference_ms: float
    avg_tracking_ms: float
    memory_usage_mb: Optional[float]
    gpu_available: bool


@router.get("", response_model=None)
async def get_status():
    """
    Get comprehensive system status.
    
    Returns:
        System status including uptime, FPS, track count, performance
    """
    state = get_state()
    status = state.get_status()
    
    return {
        "status": "ok",
        "version": APP_VERSION,
        "timestamp": datetime.utcnow().isoformat(),
        "system": status,
        "performance": {
            "fps": status.get("fps", 0),
            "frames_processed": status.get("frames_processed", 0),
            "uptime_seconds": status.get("uptime_seconds", 0)
        },
        "counts": {
            "active_tracks": status.get("active_tracks", 0),
            "total_alerts": status.get("total_alerts", 0),
            "high_risk_count": status.get("high_risk_count", 0)
        }
    }


@router.get("/health")
async def health_check():
    """
    Simple health check endpoint for load balancers.
    
    Returns:
        Health status
    """
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@router.get("/version", response_model=VersionInfo)
async def get_version():
    """
    Get version and build information.
    
    Returns:
        Version, build date, platform info
    """
    return VersionInfo(
        name=APP_NAME,
        version=APP_VERSION,
        build_date=BUILD_DATE,
        python_version=platform.python_version(),
        platform=f"{platform.system()} {platform.release()}",
        phases={
            "perception": "YOLOv8 + DeepSORT",
            "analysis": "Motion + Behavior + Crowd",
            "risk": "Weighted Multi-Signal + Temporal",
            "response": "FastAPI + Alerts",
            "semantic": "Grounding DINO (on-demand)"
        }
    )


@router.get("/performance", response_model=PerformanceMetrics)
async def get_performance():
    """
    Get performance metrics.
    
    Returns:
        FPS, inference times, memory usage
    """
    state = get_state()
    status = state.get_status()
    
    # Check GPU availability
    gpu_available = False
    try:
        import torch
        gpu_available = torch.cuda.is_available()
    except ImportError:
        pass
    
    # Estimate memory usage
    memory_mb = None
    try:
        import psutil
        process = psutil.Process(os.getpid())
        memory_mb = process.memory_info().rss / 1024 / 1024
    except ImportError:
        pass
    
    return PerformanceMetrics(
        fps=status.get("fps", 0),
        avg_inference_ms=status.get("avg_inference_ms", 0),
        avg_tracking_ms=status.get("avg_tracking_ms", 0),
        memory_usage_mb=memory_mb,
        gpu_available=gpu_available
    )

