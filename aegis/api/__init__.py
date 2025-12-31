"""
AegisAI - Smart City Risk Intelligence System
API Module

Phase 4: Response & Productization Layer
REST API for system status, events, and statistics.

Components:
- APIServer: Background server wrapper
- Routes: status, events, tracks, statistics
- APIState: Thread-safe shared state

Copyright 2024 AegisAI Project
"""

__version__ = "4.0.0"
__phase__ = "Phase 4 - Response"

from aegis.api.state import APIState, get_state
from aegis.api.app import APIServer, APIConfig, create_app

__all__ = [
    "APIState",
    "get_state",
    "APIServer",
    "APIConfig",
    "create_app",
]
