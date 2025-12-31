"""
AegisAI - Smart City Risk Intelligence System
Analysis Module

Phase 2: Analysis Layer
Transforms raw detection + tracking data into behavioral intelligence.

Components:
- TrackHistoryManager: Per-track time series storage
- MotionAnalyzer: Speed, direction, acceleration computation
- BehaviorAnalyzer: Anomaly and behavior detection
- CrowdAnalyzer: Density and crowd statistics

Copyright 2024 AegisAI Project
"""

__version__ = "2.0.0"
__phase__ = "Phase 2 - Analysis"

from aegis.analysis.analysis_types import (
    BehaviorType,
    PositionRecord,
    MotionState,
    BehaviorFlags,
    TrackAnalysis,
    DensityCell,
    CrowdMetrics,
    FrameAnalysis
)
from aegis.analysis.track_history import (
    TrackHistory,
    TrackHistoryManager
)
from aegis.analysis.motion_analyzer import (
    MotionAnalyzer,
    MotionAnalyzerConfig
)
from aegis.analysis.behavior_analyzer import (
    BehaviorAnalyzer,
    BehaviorAnalyzerConfig
)
from aegis.analysis.crowd_analyzer import (
    CrowdAnalyzer,
    CrowdAnalyzerConfig
)

__all__ = [
    # Types
    "BehaviorType",
    "PositionRecord",
    "MotionState",
    "BehaviorFlags",
    "TrackAnalysis",
    "DensityCell",
    "CrowdMetrics",
    "FrameAnalysis",
    # Track History
    "TrackHistory",
    "TrackHistoryManager",
    # Motion Analysis
    "MotionAnalyzer",
    "MotionAnalyzerConfig",
    # Behavior Analysis
    "BehaviorAnalyzer",
    "BehaviorAnalyzerConfig",
    # Crowd Analysis
    "CrowdAnalyzer",
    "CrowdAnalyzerConfig",
]
