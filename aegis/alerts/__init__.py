"""
AegisAI - Smart City Risk Intelligence System
Alert Module

Phase 4: Response & Productization Layer
Alert generation, deduplication, and dispatch system.

Components:
- AlertManager: Core alert processing
- AlertLevel/AlertChannel: Enums for classification
- Alert: Alert dataclass

Copyright 2024 AegisAI Project
"""

__version__ = "4.0.0"
__phase__ = "Phase 4 - Response"

from aegis.alerts.alert_types import (
    AlertLevel,
    AlertChannel,
    Alert,
    AlertSummary
)
from aegis.alerts.alert_manager import (
    AlertManager,
    AlertManagerConfig
)

__all__ = [
    # Types
    "AlertLevel",
    "AlertChannel",
    "Alert",
    "AlertSummary",
    # Manager
    "AlertManager",
    "AlertManagerConfig",
]
