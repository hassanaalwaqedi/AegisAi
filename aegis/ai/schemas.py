"""
AegisAI - AI Module Schemas

Pydantic models for AI orchestrator request/response structures.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from aegis.ai.language import ResponseLanguage


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
    response_language: ResponseLanguage = ResponseLanguage.ENGLISH


class VoiceRequest(BaseModel):
    """Voice transcription request."""
    audio_base64: Optional[str] = None
    text: Optional[str] = None  # Pre-transcribed text


class OperatorCommandRequest(BaseModel):
    """A command executed by the Intelligence operator against real Aegis services."""

    message: str = Field(..., min_length=2, max_length=1000)
    previous_intent: Optional[str] = Field(default=None, max_length=64)
    previous_query: Optional[str] = Field(default=None, max_length=500)
    previous_evidence_id: Optional[str] = Field(default=None, max_length=128)
    selected_camera_id: Optional[str] = Field(default=None, max_length=80)
    selected_track_id: Optional[str] = Field(default=None, max_length=128)


class OperatorTraceStep(BaseModel):
    key: str
    label: str
    status: str = "completed"


class OperatorExecutionResponse(BaseModel):
    """Typed, evidence-backed command result for the Intelligence workspace."""

    action: str
    intent: Intent
    answer: str
    panel: str
    target: Optional[str] = None
    result: Dict[str, Any] = Field(default_factory=dict)
    sources: List[SourceReference] = Field(default_factory=list)
    trace: List[OperatorTraceStep] = Field(default_factory=list)
    response_language: ResponseLanguage = ResponseLanguage.ENGLISH
    error: Optional[str] = None


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
