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

__version__ = "2.0.0"
__phase__ = "Phase 1 - Perception | Phase 2 - Analysis"
__author__ = "AegisAI Team"

# Phase 1 exports
from aegis.detection.yolo_detector import YOLODetector
from aegis.tracking.deepsort_tracker import DeepSORTTracker
from aegis.video.source import VideoSource
from aegis.video.writer import VideoWriter
from aegis.visualization.renderer import Renderer

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

__all__ = [
    # Phase 1
    "YOLODetector",
    "DeepSORTTracker",
    "VideoSource",
    "VideoWriter",
    "Renderer",
] + _ANALYSIS_EXPORTS
