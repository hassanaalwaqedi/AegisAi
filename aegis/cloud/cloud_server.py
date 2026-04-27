"""
AegisAI - Cloud Intelligence API Server

FastAPI server for the cloud layer (AWS EC2 with GPU).
Receives suspicious events from edge, runs heavy models,
and returns enhanced threat verdicts.

Deployment:
    uvicorn aegis.cloud.cloud_server:app --host 0.0.0.0 --port 8000

Phase 6: Edge/Cloud Hybrid Intelligence
"""

import base64
import logging
import time
from typing import Dict, List, Optional

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel

from aegis.fusion.risk_fusion import RiskFusionEngine
from aegis.cloud.cloud_types import CloudVerdict

logger = logging.getLogger(__name__)

# ─── API Server ───

app = FastAPI(
    title="AegisAI Cloud Intelligence",
    description="Multi-model threat analysis API (CLIP, SAM, MiDaS, SlowFast)",
    version="1.0.0",
)

# Lazy-loaded fusion engine
_fusion_engine: Optional[RiskFusionEngine] = None


def get_fusion_engine() -> RiskFusionEngine:
    """Get or create the fusion engine singleton."""
    global _fusion_engine
    if _fusion_engine is None:
        _fusion_engine = RiskFusionEngine()
    return _fusion_engine


# ─── Request/Response Models ───

class TrackPayload(BaseModel):
    track_id: Optional[int] = None
    class_name: str = "unknown"
    class_id: int = 0
    confidence: float = 0.0
    bbox: List[int] = [0, 0, 0, 0]
    object_category: str = "generic"
    is_weapon: bool = False
    is_person: bool = False
    is_animal: bool = False


class AnalyzeRequest(BaseModel):
    event_id: str = ""
    camera_id: str = ""
    timestamp: str = ""
    frame_base64: str = ""
    tracks: List[TrackPayload] = []
    edge_risk_score: float = 0.0
    triggers: List[str] = []
    frame_id: int = 0
    frame_width: int = 0
    frame_height: int = 0


class VerdictResponse(BaseModel):
    event_id: str = ""
    enhanced_risk_score: float = 0.0
    risk_level: str = "LOW"
    threat_type: Optional[str] = None
    weapon_type: Optional[str] = None
    holding_confidence: float = 0.0
    action_detected: Optional[str] = None
    context_description: str = ""
    depth_distances: Dict[str, float] = {}
    explanation: str = ""
    models_used: List[str] = []
    processing_time_ms: float = 0.0


# ─── Endpoints ───

@app.get("/health")
async def health():
    """Health check endpoint."""
    gpu_available = False
    try:
        import torch
        gpu_available = torch.cuda.is_available()
    except ImportError:
        pass
    
    return {
        "status": "ok",
        "gpu_available": gpu_available,
        "fusion_engine": repr(get_fusion_engine()),
    }


@app.post("/analyze", response_model=VerdictResponse)
async def analyze_event(
    request: AnalyzeRequest,
    x_api_key: Optional[str] = Header(None),
):
    """
    Analyze a suspicious event from the edge layer.
    
    Receives a compressed frame and track metadata,
    runs multi-model analysis, and returns a verdict.
    """
    start = time.time()
    
    # Decode frame from base64
    frame = None
    if request.frame_base64:
        try:
            frame_bytes = base64.b64decode(request.frame_base64)
            frame_array = np.frombuffer(frame_bytes, dtype=np.uint8)
            frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
        except Exception as e:
            logger.error(f"Failed to decode frame: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid frame data: {e}")
    
    if frame is None:
        raise HTTPException(status_code=400, detail="No valid frame provided")
    
    # Convert tracks to dicts
    track_dicts = [t.model_dump() for t in request.tracks]
    
    # Run fusion analysis
    engine = get_fusion_engine()
    assessments = engine.analyze(
        frame=frame,
        tracks=track_dicts,
        edge_triggers=request.triggers,
        edge_risk_score=request.edge_risk_score,
    )
    
    elapsed_ms = (time.time() - start) * 1000
    
    # Build verdict from highest-risk assessment
    if assessments:
        top = max(assessments, key=lambda a: a.risk_score)
        verdict = CloudVerdict(
            event_id=request.event_id,
            enhanced_risk_score=top.risk_score,
            risk_level=top.risk_level,
            threat_type=top.weapon_type,  # Use weapon type as threat type
            weapon_type=top.weapon_type,
            holding_confidence=top.holding_confidence,
            action_detected=top.action,
            explanation=top.explanation,
            models_used=top.contributing_models,
            processing_time_ms=elapsed_ms,
        )
    else:
        verdict = CloudVerdict(
            event_id=request.event_id,
            enhanced_risk_score=request.edge_risk_score,
            risk_level="LOW",
            explanation="No persons detected for analysis",
            models_used=["edge_filter"],
            processing_time_ms=elapsed_ms,
        )
    
    logger.info(
        f"Analyzed event {request.event_id} | "
        f"risk={verdict.risk_level} | "
        f"latency={elapsed_ms:.0f}ms"
    )
    
    return VerdictResponse(**verdict.to_dict())


@app.get("/stats")
async def get_stats():
    """Get cloud processing statistics."""
    return {
        "fusion_engine": repr(get_fusion_engine()),
    }
