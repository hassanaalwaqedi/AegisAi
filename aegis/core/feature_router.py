# === WARNING SUPPRESSION ===
import warnings
warnings.filterwarnings('ignore')
# ===========================

"""
AegisAI - Feature Router

Dynamically loads and routes to modules based on current system mode.
Ensures only relevant features are active per mode.

Copyright 2024 AegisAI Project
"""

from typing import Dict, List, Any, Optional, Callable, Type
from dataclasses import dataclass
import logging
import importlib

from aegis.core.mode_manager import (
    get_mode_manager, 
    SystemMode, 
    ModeFeatures,
    is_city_mode,
    is_restaurant_mode
)

logger = logging.getLogger(__name__)


@dataclass
class ModuleInfo:
    """Information about a loadable module."""
    name: str
    module_path: str
    class_name: str
    modes: List[SystemMode]
    loaded: bool = False
    instance: Any = None


class FeatureRouter:
    """
    Dynamically loads modules based on system mode.
    
    Example:
        >>> router = FeatureRouter()
        >>> router.load_modules_for_mode(SystemMode.RESTAURANT)
        >>> queue_analyzer = router.get_module('queue_analyzer')
    """
    
    # Module registry
    MODULES: Dict[str, ModuleInfo] = {
        # Shared modules (both modes)
        "detector": ModuleInfo(
            name="detector",
            module_path="aegis.detection.yolo_detector",
            class_name="YOLODetector",
            modes=[SystemMode.CITY, SystemMode.RESTAURANT]
        ),
        "tracker": ModuleInfo(
            name="tracker",
            module_path="aegis.tracking.deepsort_tracker",
            class_name="DeepSORTTracker",
            modes=[SystemMode.CITY, SystemMode.RESTAURANT]
        ),
        
        # CITY mode modules
        "risk_engine": ModuleInfo(
            name="risk_engine",
            module_path="aegis.risk.risk_engine",
            class_name="RiskEngine",
            modes=[SystemMode.CITY]
        ),
        "alert_manager": ModuleInfo(
            name="alert_manager",
            module_path="aegis.alerts.alert_manager",
            class_name="AlertManager",
            modes=[SystemMode.CITY]
        ),
        "behavior_analyzer": ModuleInfo(
            name="behavior_analyzer",
            module_path="aegis.analysis.behavior_analyzer",
            class_name="BehaviorAnalyzer",
            modes=[SystemMode.CITY, SystemMode.RESTAURANT]
        ),
        "crowd_analyzer": ModuleInfo(
            name="crowd_analyzer",
            module_path="aegis.analysis.crowd_analyzer",
            class_name="CrowdAnalyzer",
            modes=[SystemMode.CITY]
        ),
        
        # RESTAURANT mode modules
        "employee_monitor": ModuleInfo(
            name="employee_monitor",
            module_path="aegis.operations.employee_monitor",
            class_name="EmployeeMonitor",
            modes=[SystemMode.RESTAURANT]
        ),
        "queue_analyzer": ModuleInfo(
            name="queue_analyzer",
            module_path="aegis.operations.queue_analyzer",
            class_name="QueueAnalyzer",
            modes=[SystemMode.RESTAURANT]
        ),
        "service_kpi": ModuleInfo(
            name="service_kpi",
            module_path="aegis.operations.service_kpi",
            class_name="ServiceKPITracker",
            modes=[SystemMode.RESTAURANT]
        ),
        "safety_rules": ModuleInfo(
            name="safety_rules",
            module_path="aegis.operations.safety_rules",
            class_name="SafetyRulesChecker",
            modes=[SystemMode.RESTAURANT]
        ),
    }
    
    def __init__(self):
        """Initialize feature router."""
        self._loaded_modules: Dict[str, Any] = {}
        self._current_mode: Optional[SystemMode] = None
    
    def load_modules_for_mode(self, mode: SystemMode) -> Dict[str, Any]:
        """
        Load all modules for a specific mode.
        
        Args:
            mode: System mode to load modules for
            
        Returns:
            Dictionary of loaded module instances
        """
        if mode == self._current_mode and self._loaded_modules:
            return self._loaded_modules
        
        self._current_mode = mode
        self._loaded_modules = {}
        
        for name, info in self.MODULES.items():
            if mode in info.modes:
                try:
                    instance = self._load_module(info)
                    if instance:
                        self._loaded_modules[name] = instance
                        info.loaded = True
                        info.instance = instance
                        logger.debug(f"Loaded module: {name}")
                except Exception as e:
                    logger.warning(f"Failed to load module {name}: {e}")
        
        logger.info(f"Loaded {len(self._loaded_modules)} modules for {mode.value} mode")
        return self._loaded_modules
    
    def _load_module(self, info: ModuleInfo) -> Any:
        """Load a single module."""
        try:
            module = importlib.import_module(info.module_path)
            cls = getattr(module, info.class_name)
            # Don't instantiate - just return the class
            return cls
        except (ImportError, AttributeError) as e:
            logger.debug(f"Module {info.module_path} not available: {e}")
            return None
    
    def get_module(self, name: str) -> Optional[Any]:
        """Get a loaded module by name."""
        return self._loaded_modules.get(name)
    
    def get_module_class(self, name: str) -> Optional[Type]:
        """Get module class for instantiation."""
        return self._loaded_modules.get(name)
    
    def is_module_available(self, name: str) -> bool:
        """Check if a module is available in current mode."""
        info = self.MODULES.get(name)
        if not info:
            return False
        return self._current_mode in info.modes
    
    def get_available_modules(self) -> List[str]:
        """Get list of available module names for current mode."""
        if not self._current_mode:
            return []
        return [
            name for name, info in self.MODULES.items()
            if self._current_mode in info.modes
        ]
    
    def get_loaded_modules(self) -> Dict[str, Any]:
        """Get all currently loaded modules."""
        return self._loaded_modules.copy()


# Global singleton
_router: Optional[FeatureRouter] = None


def get_feature_router() -> FeatureRouter:
    """Get the global FeatureRouter instance."""
    global _router
    if _router is None:
        _router = FeatureRouter()
    return _router


def load_mode_modules(mode: SystemMode) -> Dict[str, Any]:
    """Load modules for a specific mode."""
    return get_feature_router().load_modules_for_mode(mode)


def get_module(name: str) -> Optional[Any]:
    """Get a loaded module by name."""
    return get_feature_router().get_module(name)
