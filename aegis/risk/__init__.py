"""
AegisAI - Smart City Risk Intelligence System
Risk Module

Phase 3: Risk Intelligence Layer
Transforms behavioral analysis into context-aware risk decisions.

Components:
- RiskEngine: Core scoring logic with explainability
- ZoneManager: Zone-based context weighting
- TemporalRiskModel: Escalation and decay over time

Copyright 2024 AegisAI Project
"""

__version__ = "3.0.0"
__phase__ = "Phase 3 - Risk Intelligence"

from aegis.risk.risk_types import (
    RiskLevel,
    RiskThresholds,
    RiskFactor,
    RiskExplanation,
    RiskScore,
    FrameRiskSummary
)
from aegis.risk.zone_context import (
    ZoneType,
    Zone,
    ZoneContext,
    ZoneManager
)
from aegis.risk.temporal_model import (
    TemporalConfig,
    TemporalState,
    TemporalRiskModel
)
from aegis.risk.risk_engine import (
    RiskWeights,
    RiskEngineConfig,
    RiskEngine
)

__all__ = [
    # Types
    "RiskLevel",
    "RiskThresholds",
    "RiskFactor",
    "RiskExplanation",
    "RiskScore",
    "FrameRiskSummary",
    # Zone Context
    "ZoneType",
    "Zone",
    "ZoneContext",
    "ZoneManager",
    # Temporal Model
    "TemporalConfig",
    "TemporalState",
    "TemporalRiskModel",
    # Risk Engine
    "RiskWeights",
    "RiskEngineConfig",
    "RiskEngine",
]
