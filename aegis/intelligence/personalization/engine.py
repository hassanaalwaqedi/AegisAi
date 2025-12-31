"""
Personalization Engine - Adaptive UI System
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
from sqlalchemy.orm import Session

from aegis.database import BehavioralSessionRepository


class UIVariant(Enum):
    DEFAULT = "default"
    SIMPLIFIED = "simplified"
    ADVANCED = "advanced"
    ONBOARDING = "onboarding"


class ContentStrategy(Enum):
    EDUCATIONAL = "educational"
    CONVERSION = "conversion"
    RETENTION = "retention"
    SUPPORT = "support"


@dataclass
class PersonalizationContext:
    """Context for personalization decisions."""
    session_id: str
    user_intent: str
    scroll_depth: float
    event_count: int
    rage_clicks: int
    hesitation_count: int
    is_returning: bool = False
    device_type: str = "desktop"


@dataclass
class PersonalizationResult:
    """Personalization recommendations."""
    ui_variant: UIVariant
    content_strategy: ContentStrategy
    feature_flags: dict = field(default_factory=dict)
    recommendations: list = field(default_factory=list)
    confidence: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            "ui_variant": self.ui_variant.value,
            "content_strategy": self.content_strategy.value,
            "feature_flags": self.feature_flags,
            "recommendations": self.recommendations,
            "confidence": self.confidence,
        }


class PersonalizationEngine:
    """AI-powered personalization for adaptive UI."""
    
    def __init__(self, db: Session = None):
        self._db = db
    
    def get_personalization(self, context: PersonalizationContext, db: Session = None) -> PersonalizationResult:
        """Get personalization recommendations based on user behavior."""
        
        # Determine UI variant
        ui_variant = self._determine_ui_variant(context)
        
        # Determine content strategy
        content_strategy = self._determine_content_strategy(context)
        
        # Generate feature flags
        feature_flags = self._generate_feature_flags(context, ui_variant)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(context)
        
        return PersonalizationResult(
            ui_variant=ui_variant,
            content_strategy=content_strategy,
            feature_flags=feature_flags,
            recommendations=recommendations,
            confidence=self._calculate_confidence(context),
        )
    
    def _determine_ui_variant(self, context: PersonalizationContext) -> UIVariant:
        """Determine best UI variant for user."""
        # New users with few events get onboarding
        if context.event_count < 5 and not context.is_returning:
            return UIVariant.ONBOARDING
        
        # Frustrated users get simplified UI
        if context.rage_clicks >= 2 or context.hesitation_count >= 3:
            return UIVariant.SIMPLIFIED
        
        # Engaged users with high scroll depth get advanced
        if context.scroll_depth >= 0.75 and context.event_count > 20:
            return UIVariant.ADVANCED
        
        return UIVariant.DEFAULT
    
    def _determine_content_strategy(self, context: PersonalizationContext) -> ContentStrategy:
        """Determine content strategy based on intent."""
        intent = context.user_intent.lower()
        
        if intent == "exploring":
            return ContentStrategy.EDUCATIONAL
        elif intent == "deciding":
            return ContentStrategy.CONVERSION
        elif intent in ["frustrated", "confused"]:
            return ContentStrategy.SUPPORT
        elif context.is_returning:
            return ContentStrategy.RETENTION
        
        return ContentStrategy.EDUCATIONAL
    
    def _generate_feature_flags(self, context: PersonalizationContext, ui_variant: UIVariant) -> dict:
        """Generate feature flags for UI."""
        flags = {
            "show_onboarding_wizard": ui_variant == UIVariant.ONBOARDING,
            "enable_advanced_filters": ui_variant == UIVariant.ADVANCED,
            "show_help_tooltips": ui_variant in [UIVariant.ONBOARDING, UIVariant.SIMPLIFIED],
            "compact_mode": context.device_type == "mobile",
            "show_quick_actions": context.event_count > 10,
            "enable_keyboard_shortcuts": ui_variant == UIVariant.ADVANCED,
            "show_conversion_cta": context.user_intent == "deciding",
            "enable_chat_support": context.rage_clicks >= 2,
        }
        return flags
    
    def _generate_recommendations(self, context: PersonalizationContext) -> list:
        """Generate personalized recommendations."""
        recommendations = []
        
        if context.user_intent == "exploring":
            recommendations.append({
                "type": "content",
                "title": "Getting Started Guide",
                "action": "view_guide",
            })
        
        if context.hesitation_count >= 2:
            recommendations.append({
                "type": "support",
                "title": "Need help? Chat with us",
                "action": "open_chat",
            })
        
        if context.scroll_depth < 0.25 and context.event_count > 5:
            recommendations.append({
                "type": "engagement",
                "title": "Explore more features",
                "action": "show_features",
            })
        
        return recommendations
    
    def _calculate_confidence(self, context: PersonalizationContext) -> float:
        """Calculate confidence in personalization."""
        base_confidence = 0.5
        
        # More data = more confidence
        if context.event_count > 10:
            base_confidence += 0.1
        if context.event_count > 50:
            base_confidence += 0.1
        
        # Known intent increases confidence
        if context.user_intent in ["engaged", "deciding", "frustrated"]:
            base_confidence += 0.15
        
        return min(base_confidence, 0.95)
