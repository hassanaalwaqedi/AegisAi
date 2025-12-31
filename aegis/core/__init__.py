"""
AegisAI - Core Module

Core utilities and infrastructure components.

Sprint 2: Production Hardening
"""

from aegis.core.shutdown import (
    ShutdownHandler,
    get_shutdown_handler,
    register_cleanup,
    is_shutting_down
)

__all__ = [
    "ShutdownHandler",
    "get_shutdown_handler",
    "register_cleanup",
    "is_shutting_down"
]
