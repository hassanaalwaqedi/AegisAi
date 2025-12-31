"""
Churn and Conversion Prediction
"""

from dataclasses import dataclass
from enum import Enum
import numpy as np


class PredictionType(Enum):
    CHURN = "churn"
    CONVERSION = "conversion"


@dataclass
class PredictionResult:
    """Prediction result with confidence and explanation"""
    session_id: str
    prediction_type: PredictionType
    probability: float
    confidence: float
    factors: list[tuple[str, float]]  # (factor_name, contribution)
    
    @property
    def risk_level(self) -> str:
        if self.probability >= 0.75:
            return "HIGH"
        elif self.probability >= 0.5:
            return "MEDIUM"
        elif self.probability >= 0.25:
            return "LOW"
        return "MINIMAL"


class ChurnPredictor:
    """Predicts churn and conversion probability per session"""
    
    # Feature weights (learned from historical data in production)
    CHURN_WEIGHTS = {
        "rage_clicks": 0.25,
        "hesitation_count": 0.20,
        "low_scroll_depth": 0.15,
        "short_session": 0.15,
        "frustrated_intent": 0.25,
    }
    
    CONVERSION_WEIGHTS = {
        "high_scroll_depth": 0.20,
        "engaged_intent": 0.25,
        "decision_path": 0.20,
        "low_frustration": 0.20,
        "time_on_site": 0.15,
    }
    
    def predict_churn(self, session_summary: dict) -> PredictionResult:
        """Predict churn probability for session"""
        factors = []
        score = 0.0
        
        # Rage clicks
        rage = min(session_summary.get("rage_clicks", 0) / 5, 1.0)
        if rage > 0:
            contribution = rage * self.CHURN_WEIGHTS["rage_clicks"]
            score += contribution
            factors.append(("Rage clicks detected", contribution))
        
        # Hesitation
        hesitation = min(session_summary.get("hesitation_count", 0) / 5, 1.0)
        if hesitation > 0:
            contribution = hesitation * self.CHURN_WEIGHTS["hesitation_count"]
            score += contribution
            factors.append(("User hesitation", contribution))
        
        # Low scroll depth
        scroll = session_summary.get("scroll_depth_max", 0)
        if scroll < 0.25:
            contribution = (1 - scroll * 4) * self.CHURN_WEIGHTS["low_scroll_depth"]
            score += contribution
            factors.append(("Low page engagement", contribution))
        
        # Frustrated intent
        intent = session_summary.get("intent", "exploring")
        if intent in ["frustrated", "confused"]:
            contribution = self.CHURN_WEIGHTS["frustrated_intent"]
            score += contribution
            factors.append(("Frustrated/confused behavior", contribution))
        
        # Normalize to probability
        probability = min(score, 1.0)
        confidence = 0.7 + (len(factors) * 0.05)  # More signals = more confidence
        
        return PredictionResult(
            session_id=session_summary.get("session_id", "unknown"),
            prediction_type=PredictionType.CHURN,
            probability=probability,
            confidence=min(confidence, 0.95),
            factors=factors,
        )
    
    def predict_conversion(self, session_summary: dict) -> PredictionResult:
        """Predict conversion probability for session"""
        factors = []
        score = 0.0
        
        # High scroll depth
        scroll = session_summary.get("scroll_depth_max", 0)
        if scroll >= 0.75:
            contribution = scroll * self.CONVERSION_WEIGHTS["high_scroll_depth"]
            score += contribution
            factors.append(("High page engagement", contribution))
        
        # Engaged intent
        intent = session_summary.get("intent", "exploring")
        if intent in ["engaged", "deciding"]:
            contribution = self.CONVERSION_WEIGHTS["engaged_intent"]
            score += contribution
            factors.append(("Engaged behavior pattern", contribution))
        
        # Decision path
        path_len = session_summary.get("decision_path_length", 0)
        if path_len >= 3:
            contribution = min(path_len / 10, 1.0) * self.CONVERSION_WEIGHTS["decision_path"]
            score += contribution
            factors.append(("Active exploration", contribution))
        
        # Low frustration
        rage = session_summary.get("rage_clicks", 0)
        hesitation = session_summary.get("hesitation_count", 0)
        if rage == 0 and hesitation < 2:
            contribution = self.CONVERSION_WEIGHTS["low_frustration"]
            score += contribution
            factors.append(("Smooth user experience", contribution))
        
        probability = min(score, 1.0)
        confidence = 0.65 + (len(factors) * 0.05)
        
        return PredictionResult(
            session_id=session_summary.get("session_id", "unknown"),
            prediction_type=PredictionType.CONVERSION,
            probability=probability,
            confidence=min(confidence, 0.95),
            factors=factors,
        )
