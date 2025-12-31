# === WARNING SUPPRESSION (MUST BE FIRST) ===
import warnings
import os
warnings.filterwarnings('ignore')
os.environ['PYTHONWARNINGS'] = 'ignore'
# === END WARNING SUPPRESSION ===

"""
AegisAI - Mode Manager

Manages system operation modes:
- CITY: Smart City Risk Monitoring
- RESTAURANT: Employee & Operational Intelligence

Copyright 2024 AegisAI Project
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional
import logging

logger = logging.getLogger(__name__)


class SystemMode(Enum):
    """Available system operation modes."""
    CITY = "city"
    RESTAURANT = "restaurant"
    
    @classmethod
    def from_string(cls, value: str) -> 'SystemMode':
        """Parse mode from string."""
        value = value.lower().strip()
        if value in ("city", "smart_city", "risk"):
            return cls.CITY
        elif value in ("restaurant", "shop", "retail", "operations"):
            return cls.RESTAURANT
        else:
            raise ValueError(f"Unknown mode: {value}. Use 'city' or 'restaurant'")


@dataclass
class ModeFeatures:
    """Features available for each mode."""
    # Shared features (always enabled)
    detection: bool = True
    tracking: bool = True
    video_io: bool = True
    visualization: bool = True
    api: bool = True
    
    # CITY mode features
    risk_scoring: bool = False
    alerts: bool = False
    zones: bool = False
    semantic: bool = False
    crowd_analysis: bool = False
    behavior_analysis: bool = False
    
    # RESTAURANT mode features
    employee_monitoring: bool = False
    queue_analysis: bool = False
    service_kpi: bool = False
    safety_rules: bool = False
    staff_heatmap: bool = False
    table_tracking: bool = False


@dataclass
class PrivacyConfig:
    """Privacy settings for data handling."""
    # Facial recognition disabled by default
    facial_recognition: bool = False
    biometric_storage: bool = False
    
    # Anonymous tracking
    anonymous_tracking: bool = True
    track_ids_only: bool = True
    
    # Data retention
    retention_hours: int = 24
    auto_cleanup: bool = True
    
    # Logging
    log_personal_data: bool = False


class ModeManager:
    """
    Manages system operation mode and feature availability.
    
    Example:
        >>> manager = ModeManager()
        >>> manager.set_mode(SystemMode.RESTAURANT)
        >>> features = manager.get_features()
        >>> print(features.employee_monitoring)  # True
    """
    
    _instance: Optional['ModeManager'] = None
    
    def __new__(cls):
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize mode manager."""
        if self._initialized:
            return
        
        self._mode = SystemMode.CITY  # Default mode
        self._features = self._get_mode_features(self._mode)
        self._privacy = PrivacyConfig()
        self._initialized = True
        
        logger.info(f"ModeManager initialized with mode: {self._mode.value}")
    
    @property
    def mode(self) -> SystemMode:
        """Get current system mode."""
        return self._mode
    
    @property
    def features(self) -> ModeFeatures:
        """Get current feature set."""
        return self._features
    
    @property
    def privacy(self) -> PrivacyConfig:
        """Get privacy configuration."""
        return self._privacy
    
    def set_mode(self, mode: SystemMode) -> None:
        """
        Switch system mode.
        
        Args:
            mode: New system mode
        """
        if mode == self._mode:
            return
        
        old_mode = self._mode
        self._mode = mode
        self._features = self._get_mode_features(mode)
        
        logger.info(f"System mode changed: {old_mode.value} -> {mode.value}")
    
    def _get_mode_features(self, mode: SystemMode) -> ModeFeatures:
        """Get features for a specific mode."""
        features = ModeFeatures()
        
        if mode == SystemMode.CITY:
            # Enable city-specific features
            features.risk_scoring = True
            features.alerts = True
            features.zones = True
            features.semantic = True
            features.crowd_analysis = True
            features.behavior_analysis = True
            
        elif mode == SystemMode.RESTAURANT:
            # Enable restaurant-specific features
            features.employee_monitoring = True
            features.queue_analysis = True
            features.service_kpi = True
            features.safety_rules = True
            features.staff_heatmap = True
            features.table_tracking = True
            # Also enable some shared analysis
            features.behavior_analysis = True
        
        return features
    
    def is_feature_enabled(self, feature_name: str) -> bool:
        """Check if a feature is enabled in current mode."""
        return getattr(self._features, feature_name, False)
    
    def get_enabled_features(self) -> List[str]:
        """Get list of enabled feature names."""
        return [
            name for name, value in self._features.__dict__.items()
            if value is True
        ]
    
    def get_api_routes(self) -> List[str]:
        """Get API routes available in current mode."""
        routes = ["/status", "/tracks", "/mode"]  # Always available
        
        if self._mode == SystemMode.CITY:
            routes.extend([
                "/events", "/statistics", "/zones",
                "/intelligence", "/semantic"
            ])
        elif self._mode == SystemMode.RESTAURANT:
            routes.extend([
                "/operations/staff", "/operations/queue",
                "/operations/kpi", "/operations/safety"
            ])
        
        return routes
    
    def to_dict(self) -> Dict:
        """Serialize to dictionary."""
        return {
            "mode": self._mode.value,
            "features": {
                name: value
                for name, value in self._features.__dict__.items()
            },
            "privacy": {
                name: value
                for name, value in self._privacy.__dict__.items()
            },
            "available_routes": self.get_api_routes()
        }


# Global singleton access
_manager: Optional[ModeManager] = None


def get_mode_manager() -> ModeManager:
    """Get the global ModeManager instance."""
    global _manager
    if _manager is None:
        _manager = ModeManager()
    return _manager


def get_current_mode() -> SystemMode:
    """Get the current system mode."""
    return get_mode_manager().mode


def set_mode(mode: SystemMode) -> None:
    """Set the current system mode."""
    get_mode_manager().set_mode(mode)


def is_city_mode() -> bool:
    """Check if running in CITY mode."""
    return get_current_mode() == SystemMode.CITY


def is_restaurant_mode() -> bool:
    """Check if running in RESTAURANT mode."""
    return get_current_mode() == SystemMode.RESTAURANT
