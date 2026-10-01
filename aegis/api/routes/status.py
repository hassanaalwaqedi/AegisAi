"""
AegisAI - Smart City Risk Intelligence System
API Routes - Status & System Information

GET /status - System health, performance, and version info
GET /status/health - Simple health check
GET /status/version - Version and build info

Phase 4: Response & Productization Layer
"""

import os
import subprocess
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
    inference_device: Optional[str] = None
    precision: Optional[str] = None
    preprocessing_ms: Optional[float] = None
    inference_ms: Optional[float] = None
    postprocessing_ms: Optional[float] = None
    end_to_end_frame_ms: Optional[float] = None
    effective_inference_fps: Optional[float] = None
    gpu_utilization_percent: Optional[float] = None
    gpu_vram_mb: Optional[float] = None
    process_cpu_percent: Optional[float] = None


def _active_model_capabilities(state_status):
    """Prefer the detector owned by live camera ingestion over the preload model."""
    try:
        from aegis.api.routes.cameras import get_camera_manager
        ingestion = get_camera_manager().ingestion
        if getattr(ingestion, "_detector", None) is not None:
            return ingestion.get_model_capabilities()
    except Exception:
        pass
    return {
        "general_detector": state_status.get("person_detector", {}).get("runtime", {}),
        "weapon_detector": state_status.get("weapon_detector", {}),
        "threat_detector": state_status.get("threat_detector", {}),
    }


def _runtime_resources():
    """Sample resource state from the API process/container without exposing IDs."""
    values = {"gpu_utilization_percent": None, "gpu_vram_mb": None, "process_cpu_percent": None}
    try:
        import psutil
        values["process_cpu_percent"] = round(psutil.Process(os.getpid()).cpu_percent(interval=None), 1)
    except Exception:
        pass
    try:
        import torch
        if torch.cuda.is_available():
            values["gpu_vram_mb"] = round(torch.cuda.memory_allocated() / 1024 / 1024, 1)
    except Exception:
        pass
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=1.0,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            values["gpu_utilization_percent"] = float(result.stdout.strip().splitlines()[0])
    except Exception:
        pass
    return values


@router.get("", response_model=None)
async def get_status():
    """
    Get comprehensive system status.
    
    Returns:
        System status including uptime, FPS, track count, performance
    """
    state = get_state()
    status = state.get_status()
    active_model = _active_model_capabilities(status)
    general_detector = active_model.get("general_detector", {})
    weapon_detector = active_model.get("weapon_detector", {}).get("runtime", active_model.get("weapon_detector", {}))
    threat_detector = active_model.get("threat_detector", {}).get("runtime", active_model.get("threat_detector", {}))
    threat_enabled = bool(active_model.get("threat_detector", {}).get("enabled"))
    # A configured detector is not the same thing as one that the running
    # pipeline has instantiated.  Only an initialized, enabled threat runtime
    # participates in health readiness.  This keeps the status truthful while
    # allowing an isolated general-detector runtime to report as ready.
    threat_initialized = bool(threat_detector.get("backend") or threat_detector.get("model"))
    vision = {
        "status": "ready" if general_detector.get("ready") and (
            not threat_enabled or not threat_initialized or threat_detector.get("ready")
        ) else "degraded",
        "general_detector": general_detector,
        "weapon_detector": weapon_detector,
        "threat_detector": threat_detector,
    }
    
    return {
        "status": "ok",
        "version": APP_VERSION,
        "timestamp": datetime.utcnow().isoformat(),
        "system": status,
        "vision": vision,
        "performance": {
            "fps": status.get("current_fps", status.get("fps", 0)),
            "frames_processed": status.get("frames_processed", 0),
            "uptime_seconds": status.get("uptime_seconds", 0),
            "inference_device": general_detector.get("device"),
            "precision": general_detector.get("precision"),
            "inference": general_detector.get("performance", {}),
            **_runtime_resources(),
        },
        "counts": {
            "active_tracks": status.get("active_tracks", 0),
            "total_alerts": status.get("total_alerts", 0),
            "high_risk_count": status.get("high_risk_count", 0)
        },
        "model": {
            "model_name": status.get("model_name", ""),
            "supported_classes": status.get("supported_classes", []),
            "weapon_detection_supported": status.get("weapon_detection_supported", False),
            "person_detector": active_model.get("person_detector", status.get("person_detector", {})),
            "weapon_detector": active_model.get("weapon_detector", status.get("weapon_detector", {})),
            "threat_detector": active_model.get("threat_detector", status.get("threat_detector", {})),
            "action_recognition_supported": status.get("action_recognition_supported", False),
            "pose_estimation_supported": status.get("pose_estimation_supported", False),
            "semantic_verification_supported": status.get("semantic_verification_supported", False),
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
    general = _active_model_capabilities(status).get("general_detector", {})
    measured = general.get("performance", {})
    resources = _runtime_resources()
    
    # Check GPU availability
    gpu_available = False
    try:
        import torch
        gpu_available = bool(getattr(getattr(torch, "cuda", None), "is_available", lambda: False)())
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
        avg_inference_ms=measured.get("avg_inference_ms") or status.get("avg_inference_ms", 0),
        avg_tracking_ms=status.get("avg_tracking_ms", 0),
        memory_usage_mb=memory_mb,
        gpu_available=gpu_available,
        inference_device=general.get("device"),
        precision=general.get("precision"),
        preprocessing_ms=measured.get("avg_preprocessing_ms"),
        inference_ms=measured.get("avg_inference_ms"),
        postprocessing_ms=measured.get("avg_postprocessing_ms"),
        end_to_end_frame_ms=measured.get("avg_end_to_end_ms"),
        effective_inference_fps=measured.get("effective_fps"),
        gpu_utilization_percent=resources.get("gpu_utilization_percent"),
        gpu_vram_mb=resources.get("gpu_vram_mb"),
        process_cpu_percent=resources.get("process_cpu_percent"),
    )

