"""Typed contracts for the Gemini Live Intelligence voice gateway.

These envelopes intentionally carry only PCM audio, transcriptions, approved
citations, and allow-listed UI commands.  They never carry an API key, a raw
backend route, or an arbitrary model-generated navigation target.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from aegis.intelligence.context_schemas import Availability


class LiveModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class VoiceState(str, Enum):
    OFF = "off"
    CONNECTING = "connecting"
    READY = "ready"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    ERROR = "error"


class LiveCapabilities(LiveModel):
    availability: Availability
    reason: Optional[str] = None
    native_audio: bool = Field(default=False, alias="nativeAudio")
    input_transcription: bool = Field(default=False, alias="inputTranscription")
    output_transcription: bool = Field(default=False, alias="outputTranscription")
    input_sample_rate: Optional[int] = Field(default=None, alias="inputSampleRate")
    output_sample_rate: Optional[int] = Field(default=None, alias="outputSampleRate")
    push_to_talk: Availability = Field(alias="pushToTalk")
    websocket_protocol: str = Field(default="aegis-live-v1", alias="websocketProtocol")


class LiveSessionCreate(LiveModel):
    """The browser provides no credential; API-key auth precedes this body."""

    requested_at: Optional[datetime] = Field(default=None, alias="requestedAt")
    # An optional opaque identifier for a server-validated HIGH/CRITICAL
    # Intelligence record. The browser never sends alert wording or severity;
    # the Live gateway re-resolves this identifier against current context.
    audible_alert_id: Optional[str] = Field(default=None, alias="audibleAlertId", max_length=256)


class LiveSessionResponse(LiveModel):
    session_id: str = Field(alias="sessionId")
    connection_token: str = Field(alias="connectionToken")
    expires_at: datetime = Field(alias="expiresAt")
    correlation_id: str = Field(alias="correlationId")
    capabilities: LiveCapabilities


class LiveCitation(LiveModel):
    evidence_id: str = Field(alias="evidenceId")
    kind: Literal[
        "camera",
        "event",
        "alert",
        "track",
        "detection",
        "recording",
        "statistics",
        "health",
    ]
    label: str
    camera_id: Optional[str] = Field(default=None, alias="cameraId")
    observed_at: Optional[datetime] = Field(default=None, alias="observedAt")
    availability: Availability


class UICommandKind(str, Enum):
    OPEN_CAMERAS = "open_cameras"
    SHOW_TRACK_EVIDENCE = "show_track_evidence"
    OPEN_SEMANTIC_EVIDENCE = "open_semantic_evidence"
    SHOW_RISK_EVIDENCE = "show_risk_evidence"
    FOCUS_HEALTH = "focus_health"


class SafeUICommand(LiveModel):
    """A small enum rather than an LLM-provided URL or JavaScript action."""

    kind: UICommandKind
    target_id: Optional[str] = Field(default=None, alias="targetId")
    camera_id: Optional[str] = Field(default=None, alias="cameraId")


class LiveToolResult(LiveModel):
    schema_version: Literal["1.0"] = Field(default="1.0", alias="schemaVersion")
    tool: str
    availability: Availability
    observed_at: datetime = Field(alias="observedAt")
    reason: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    citations: List[LiveCitation] = Field(default_factory=list)
    ui_command: Optional[SafeUICommand] = Field(default=None, alias="uiCommand")


class ToolAuditRecord(LiveModel):
    schema_version: Literal["1.0"] = Field(default="1.0", alias="schemaVersion")
    tool: str
    correlation_id: str = Field(alias="correlationId")
    operator_id: str = Field(alias="operatorId")
    session_id: str = Field(alias="sessionId")
    arguments: Dict[str, Any] = Field(default_factory=dict)
    result_status: Availability = Field(alias="resultStatus")
    latency_ms: float = Field(alias="latencyMs")
    evidence_ids: List[str] = Field(default_factory=list, alias="evidenceIds")
    observed_at: datetime = Field(alias="observedAt")


class BrowserVoiceEnvelope(LiveModel):
    version: Literal["1.0"] = "1.0"
    type: Literal["audio", "text", "audio_end", "interrupt", "stop", "ping"]
    data: Optional[str] = None
    mime_type: Optional[str] = Field(default=None, alias="mimeType")


class ServerVoiceEnvelope(LiveModel):
    version: Literal["1.0"] = "1.0"
    type: Literal["session_ready", "state", "transcript", "citations", "ui_command", "tool_activity", "turn_complete", "interrupted", "error", "pong"]
    state: Optional[VoiceState] = None
    session_id: Optional[str] = Field(default=None, alias="sessionId")
    input_sample_rate: Optional[int] = Field(default=None, alias="inputSampleRate")
    output_sample_rate: Optional[int] = Field(default=None, alias="outputSampleRate")
    speaker: Optional[Literal["operator", "aegis"]] = None
    text: Optional[str] = None
    is_final: Optional[bool] = Field(default=None, alias="isFinal")
    turn_id: Optional[str] = Field(default=None, alias="turnId")
    citations: List[LiveCitation] = Field(default_factory=list)
    ui_command: Optional[SafeUICommand] = Field(default=None, alias="uiCommand")
    tool: Optional[str] = None
    tool_status: Optional[Literal["calling", "completed", "failed"]] = Field(default=None, alias="toolStatus")
    recoverable: Optional[bool] = None
    code: Optional[str] = None
    message: Optional[str] = None
    correlation_id: Optional[str] = Field(default=None, alias="correlationId")
