# === WARNING SUPPRESSION (MUST BE FIRST) ===
import warnings
import os
warnings.filterwarnings('ignore')
warnings.filterwarnings('ignore', category=RuntimeWarning)
warnings.filterwarnings('ignore', category=DeprecationWarning)
os.environ['PYTHONWARNINGS'] = 'ignore'
# === END WARNING SUPPRESSION ===

"""
AegisAI - Smart City Risk Intelligence System
Core Package

Phase 1: Perception Layer
- Real-time object detection (persons and vehicles)
- Multi-object tracking with unique IDs
- Video processing and visualization

Phase 2: Analysis Layer
- Track history and time series management
- Motion analysis (speed, direction, acceleration)
- Behavior detection (loitering, anomalies)
- Crowd analysis (density, hotspots)

Copyright 2024 AegisAI Project
"""

__version__ = "4.0.0"
__phase__ = "Phase 1-6 | Hybrid Edge/Cloud Intelligence"
__author__ = "AegisAI Team"

# Phase 1 exports (conditional - requires ultralytics)
try:
    from aegis.detection.yolo_detector import YOLODetector, Detection
    _PHASE1_EXPORTS = [
        "YOLODetector",
        "Detection",
    ]
except ImportError:
    _PHASE1_EXPORTS = []

# Phase 1 tracking (ByteTrack - default, DeepSORT - optional)
try:
    from aegis.tracking.bytetrack_tracker import ByteTrackTracker
    _TRACKING_EXPORTS = ["ByteTrackTracker"]
except ImportError:
    _TRACKING_EXPORTS = []

try:
    from aegis.tracking.deepsort_tracker import DeepSORTTracker
    _TRACKING_EXPORTS.append("DeepSORTTracker")
except ImportError:
    pass

# Phase 1 risk (ProximityRiskEngine - lightweight CPU)
try:
    from aegis.risk.proximity_risk import ProximityRiskEngine, ProximityRiskAssessment
    _RISK_EXPORTS = ["ProximityRiskEngine", "ProximityRiskAssessment"]
except ImportError:
    _RISK_EXPORTS = []

# Phase 1 edge pipeline
try:
    from aegis.edge.edge_pipeline import EdgePipeline
    from aegis.edge.pipeline_types import PipelineResult
    _EDGE_EXPORTS = ["EdgePipeline", "PipelineResult"]
except ImportError:
    _EDGE_EXPORTS = []

# Phase 2 exports (conditional)
try:
    from aegis.analysis import (
        TrackHistoryManager,
        MotionAnalyzer,
        BehaviorAnalyzer,
        CrowdAnalyzer,
        FrameAnalysis,
        TrackAnalysis,
        MotionState,
        BehaviorFlags,
        CrowdMetrics
    )
    _ANALYSIS_EXPORTS = [
        "TrackHistoryManager",
        "MotionAnalyzer",
        "BehaviorAnalyzer",
        "CrowdAnalyzer",
        "FrameAnalysis",
        "TrackAnalysis",
        "MotionState",
        "BehaviorFlags",
        "CrowdMetrics"
    ]
except ImportError:
    _ANALYSIS_EXPORTS = []

# Phase 6 cloud exports (lightweight dependencies)
try:
    from aegis.edge.edge_risk_filter import EdgeRiskFilter
    from aegis.edge.event_types import EdgeAssessment, SuspiciousEvent, TrackSummary
    from aegis.cloud.cloud_client import CloudClient
    from aegis.cloud.cloud_types import CloudVerdict
    _CLOUD_EXPORTS = [
        "EdgeRiskFilter",
        "EdgeAssessment",
        "SuspiciousEvent",
        "TrackSummary",
        "CloudClient",
        "CloudVerdict",
    ]
except ImportError:
    _CLOUD_EXPORTS = []

__all__ = (
    _PHASE1_EXPORTS + _TRACKING_EXPORTS + _RISK_EXPORTS +
    _EDGE_EXPORTS + _ANALYSIS_EXPORTS + _CLOUD_EXPORTS
)

