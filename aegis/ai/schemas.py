"""
AegisAI - AI Module Schemas

Pydantic models for AI orchestrator request/response structures.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Intent(str, Enum):
    """Classified user intent."""
    INVESTIGATION = "Investigation"
    INCIDENT = "Incident"
    REPORT = "Report"
    SEARCH = "Search"
    ANALYTICS = "Analytics"
    RISK = "Risk"
    CAMERA = "Camera"
    TRACKING = "Tracking"
    HEALTH = "Health"
    KNOWLEDGE = "Knowledge"
    SETTINGS = "Settings"
    GENERAL = "General"


class ChatRequest(BaseModel):
    """Incoming chat request from frontend."""
    message: str = Field(..., min_length=1, max_length=2000)
    conversation_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class ActionItem(BaseModel):
    """An action the AI suggests the frontend should take."""
    type: str  # "navigate", "open_panel", "highlight", "filter"
    target: str  # URL, camera_id, panel_id, etc.
    label: str


class SourceReference(BaseModel):
    """Data source the AI used to generate the answer."""
    type: str  # "camera", "event", "alert", "database", "metric"
    id: Optional[str] = None
    label: str


class ChatResponse(BaseModel):
    """Structured response from AI orchestrator."""
    intent: Intent = Intent.GENERAL
    answer: str = ""
    actions: List[ActionItem] = Field(default_factory=list)
    sources: List[SourceReference] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    latency_ms: float = 0.0
    error: Optional[str] = None


class VoiceRequest(BaseModel):
    """Voice transcription request."""
    audio_base64: Optional[str] = None
    text: Optional[str] = None  # Pre-transcribed text


class SystemContext(BaseModel):
    """Collected system state for Gemini prompt."""
    timestamp: str = ""
    cameras_online: int = 0
    cameras_total: int = 0
    active_incidents: int = 0
    total_alerts_today: int = 0
    system_health: str = "unknown"
    high_risk_count: int = 0
    recent_events: List[Dict[str, Any]] = Field(default_factory=list)
    active_tracks: int = 0
    database_status: str = "unknown"
    pipeline_status: str = "unknown"
