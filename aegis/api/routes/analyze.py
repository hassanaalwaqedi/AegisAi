"""
AegisAI - Browser Stream Analysis API

Endpoint to analyze frames from browser webcam.
Runs same AI pipeline as main.py but for remote frames.

Copyright 2024 AegisAI Project
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import base64
import numpy as np
import cv2
from datetime import datetime

from aegis.api.security import verify_api_key

router = APIRouter(prefix="/analyze", tags=["analysis"])


class FrameRequest(BaseModel):
    """Request with base64 encoded frame."""
    frame: str  # Base64 encoded JPEG/PNG
    include_risk: bool = True
    include_tracking: bool = True


class Detection(BaseModel):
    """Single detection result."""
    class_name: str
    confidence: float
    bbox: List[int]  # [x1, y1, x2, y2]
    track_id: Optional[int] = None
    risk_level: Optional[str] = None
    risk_score: Optional[float] = None


class AnalysisResponse(BaseModel):
    """Analysis response with all detections."""
    success: bool
    frame_id: str
    timestamp: str
    detections: List[Detection]
    person_count: int
    vehicle_count: int
    max_risk_level: str
    max_risk_score: float
    processing_time_ms: float


# Global detector reference (lazy loaded)
_detector = None
_tracker = None
_risk_scorer = None


def get_detector():
    """Lazy load the YOLO detector."""
    global _detector
    if _detector is None:
        try:
            from aegis.detection.yolo_detector import YOLODetector
            _detector = YOLODetector()
        except Exception as e:
            print(f"Failed to load detector: {e}")
            return None
    return _detector


def get_tracker():
    """Lazy load the tracker."""
    global _tracker
    if _tracker is None:
        try:
            from aegis.tracking.byte_tracker import ByteTracker
            _tracker = ByteTracker()
        except Exception as e:
            print(f"Failed to load tracker: {e}")
            return None
    return _tracker


def get_risk_scorer():
    """Lazy load risk scorer."""
    global _risk_scorer
    if _risk_scorer is None:
        try:
            from aegis.risk.risk_scorer import RiskScorer
            _risk_scorer = RiskScorer()
        except Exception as e:
            print(f"Failed to load risk scorer: {e}")
            return None
    return _risk_scorer


def decode_frame(base64_frame: str) -> np.ndarray:
    """Decode base64 frame to numpy array."""
    # Remove data URL prefix if present
    if ',' in base64_frame:
        base64_frame = base64_frame.split(',')[1]
    
    # Decode base64
    frame_bytes = base64.b64decode(base64_frame)
    
    # Convert to numpy array
    nparr = np.frombuffer(frame_bytes, np.uint8)
    
    # Decode image
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if frame is None:
        raise ValueError("Failed to decode frame")
    
    return frame


@router.post("/frame", response_model=AnalysisResponse, dependencies=[Depends(verify_api_key)])
async def analyze_frame(request: FrameRequest):
    """
    Analyze a single frame from browser webcam.
    
    Runs YOLO detection, tracking, and risk scoring.
    Same pipeline as main.py but for remote frames.
    """
    import time
    start_time = time.time()
    
    try:
        # Decode frame
        frame = decode_frame(request.frame)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid frame: {str(e)}")
    
    # Get detector
    detector = get_detector()
    if detector is None:
        # Return demo response if detector not available
        return AnalysisResponse(
            success=False,
            frame_id=f"frame_{datetime.utcnow().timestamp()}",
            timestamp=datetime.utcnow().isoformat(),
            detections=[],
            person_count=0,
            vehicle_count=0,
            max_risk_level="LOW",
            max_risk_score=0.0,
            processing_time_ms=0.0
        )
    
    # Run detection
    try:
        detections_raw = detector.detect(frame)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Detection failed: {str(e)}")
    
    # Process detections
    detections = []
    person_count = 0
    vehicle_count = 0
    max_risk_score = 0.0
    
    tracker = get_tracker() if request.include_tracking else None
    risk_scorer = get_risk_scorer() if request.include_risk else None
    
    # Apply tracking if available
    if tracker and len(detections_raw) > 0:
        try:
            tracked = tracker.update(detections_raw, frame)
            detections_raw = tracked
        except:
            pass
    
    for det in detections_raw:
        class_name = det.get('class_name', det.get('label', 'unknown'))
        confidence = det.get('confidence', det.get('score', 0.0))
        bbox = det.get('bbox', det.get('box', [0, 0, 0, 0]))
        track_id = det.get('track_id')
        
        # Count by class
        if class_name.lower() == 'person':
            person_count += 1
        elif class_name.lower() in ['car', 'truck', 'bus', 'motorcycle', 'bicycle']:
            vehicle_count += 1
        
        # Calculate risk if enabled
        risk_level = "LOW"
        risk_score = 0.1
        
        if risk_scorer:
            try:
                risk_result = risk_scorer.calculate_risk(det, frame)
                risk_level = risk_result.get('level', 'LOW')
                risk_score = risk_result.get('score', 0.1)
            except:
                pass
        
        max_risk_score = max(max_risk_score, risk_score)
        
        detections.append(Detection(
            class_name=class_name,
            confidence=confidence,
            bbox=bbox if isinstance(bbox, list) else list(bbox),
            track_id=track_id,
            risk_level=risk_level,
            risk_score=risk_score
        ))
    
    # Determine max risk level
    if max_risk_score >= 0.8:
        max_risk_level = "CRITICAL"
    elif max_risk_score >= 0.6:
        max_risk_level = "HIGH"
    elif max_risk_score >= 0.3:
        max_risk_level = "MEDIUM"
    else:
        max_risk_level = "LOW"
    
    processing_time = (time.time() - start_time) * 1000
    
    return AnalysisResponse(
        success=True,
        frame_id=f"frame_{datetime.utcnow().timestamp()}",
        timestamp=datetime.utcnow().isoformat(),
        detections=detections,
        person_count=person_count,
        vehicle_count=vehicle_count,
        max_risk_level=max_risk_level,
        max_risk_score=max_risk_score,
        processing_time_ms=processing_time
    )


@router.get("/health")
async def analysis_health():
    """Check if analysis pipeline is ready."""
    detector = get_detector()
    return {
        "detector_loaded": detector is not None,
        "tracker_loaded": get_tracker() is not None,
        "risk_scorer_loaded": get_risk_scorer() is not None,
        "ready": detector is not None
    }
