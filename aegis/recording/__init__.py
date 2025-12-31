"""
AegisAI - Recording Module

Risk-based video recording with pre-event buffering.

Copyright 2024 AegisAI Project
"""

from aegis.recording.risk_recorder import RiskRecorder
from aegis.recording.models import RecordingEvent, RecordingMetadata

__all__ = [
    "RiskRecorder",
    "RecordingEvent",
    "RecordingMetadata",
]
