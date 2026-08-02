# Suppress only the known numpy MINGW warning that crashes Python 3.14 on Windows.
# All other warnings should surface — blanket suppression hides real bugs.
import warnings
import os
warnings.filterwarnings('ignore', message='.*Numpy built with MINGW.*')
os.environ.setdefault('PYTHONWARNINGS', 'default')

# Configure structured logging on first import
from aegis.core.logging import setup_logging as _setup_logging
_setup_logging(
    debug=os.getenv("AEGIS_DEBUG", "").lower() in ("1", "true", "yes"),
    level=os.getenv("AEGIS_LOG_LEVEL") or None,
)

"""
AegisAI - AI Security Operating System
Core Package

Phase 1: Perception Layer (Detection + Tracking)
Phase 2: Analysis Layer (Motion + Behavior + Crowd)
Phase 3: Risk Intelligence Layer
Phase 4: Response Layer (API + Alerts)
Phase 5: Semantic Intelligence Layer
Phase 6: Edge/Cloud Hybrid Intelligence

Copyright 2024 AegisAI Project
"""

__version__ = "5.0.0"
__phase__ = "Phase 0-6 | AI Security Operating System"
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

