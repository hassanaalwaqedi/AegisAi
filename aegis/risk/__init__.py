"""Aegis context-aware risk intelligence public API."""

__version__ = "3.0.0"
__phase__ = "Phase 6 - Situation Intelligence"

from aegis.risk.risk_types import RiskLevel, RiskThresholds, RiskFactor, RiskExplanation, RiskScore, FrameRiskSummary
from aegis.risk.zone_context import ZoneType, Zone, ZoneContext, ZoneManager
from aegis.risk.temporal_model import TemporalConfig, TemporalState, TemporalRiskModel
from aegis.risk.risk_engine import RiskWeights, RiskEngineConfig, RiskEngine
from aegis.risk.proximity_risk import ProximityRiskEngine, ProximityRiskAssessment, ProximityRiskConfig
from aegis.risk.person_weapon_association import PersonWeaponAssociationEngine, WeaponAssociation
from aegis.risk.weapon_aggression import ThreatContext, WeaponAggressionConfig, WeaponAggressionRiskLayer
from aegis.risk.situation_intelligence import SituationIntelligence, SituationRiskConfig, SituationEvidence, SituationAssessment

__all__ = [
    "RiskLevel", "RiskThresholds", "RiskFactor", "RiskExplanation", "RiskScore", "FrameRiskSummary",
    "ZoneType", "Zone", "ZoneContext", "ZoneManager", "TemporalConfig", "TemporalState", "TemporalRiskModel",
    "RiskWeights", "RiskEngineConfig", "RiskEngine", "ProximityRiskEngine", "ProximityRiskAssessment", "ProximityRiskConfig",
    "PersonWeaponAssociationEngine", "WeaponAssociation", "ThreatContext", "WeaponAggressionConfig", "WeaponAggressionRiskLayer",
    "SituationIntelligence", "SituationRiskConfig", "SituationEvidence", "SituationAssessment",
]
