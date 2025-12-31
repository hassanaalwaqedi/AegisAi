"""
AI-Driven Feature Flags Service
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session


@dataclass
class FeatureFlag:
    """Feature flag with targeting rules."""
    name: str
    enabled: bool
    rollout_percentage: float = 100.0
    targeting_rules: dict = None
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.targeting_rules is None:
            self.targeting_rules = {}


class FeatureFlagService:
    """Manages AI-driven feature flags."""
    
    DEFAULT_FLAGS = {
        "nlq_enabled": FeatureFlag("nlq_enabled", True, 100.0),
        "advanced_analytics": FeatureFlag("advanced_analytics", True, 50.0),
        "ai_insights": FeatureFlag("ai_insights", True, 100.0),
        "adaptive_ui": FeatureFlag("adaptive_ui", True, 80.0),
        "personalization": FeatureFlag("personalization", True, 70.0),
        "executive_dashboard": FeatureFlag("executive_dashboard", True, 100.0),
        "dark_mode": FeatureFlag("dark_mode", True, 100.0),
        "rtl_support": FeatureFlag("rtl_support", True, 100.0),
    }
    
    def __init__(self, db: Session = None):
        self._db = db
        self._flags: dict[str, FeatureFlag] = self.DEFAULT_FLAGS.copy()
    
    def is_enabled(self, flag_name: str, user_context: dict = None) -> bool:
        """Check if a feature flag is enabled for user."""
        if flag_name not in self._flags:
            return False
        
        flag = self._flags[flag_name]
        
        if not flag.enabled:
            return False
        
        # Simple rollout percentage check
        if flag.rollout_percentage < 100:
            # In production, use consistent hashing based on user_id
            import random
            if random.random() * 100 > flag.rollout_percentage:
                return False
        
        # Check targeting rules
        if user_context and flag.targeting_rules:
            for rule_key, rule_value in flag.targeting_rules.items():
                if user_context.get(rule_key) != rule_value:
                    return False
        
        return True
    
    def get_all_flags(self, user_context: dict = None) -> dict[str, bool]:
        """Get all flag states for user."""
        return {
            name: self.is_enabled(name, user_context)
            for name in self._flags
        }
    
    def set_flag(self, name: str, enabled: bool, rollout: float = 100.0):
        """Set or update a feature flag."""
        self._flags[name] = FeatureFlag(name, enabled, rollout)
    
    def get_flag(self, name: str) -> Optional[FeatureFlag]:
        """Get a specific feature flag."""
        return self._flags.get(name)
