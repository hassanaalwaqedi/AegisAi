"""Typed, source-fresh contract for the Intelligence operational view.

The models intentionally distinguish a measured zero from an unavailable
source.  Counts are therefore optional when their source cannot be queried.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ContextModel(BaseModel):
    """Base model that exposes the public API's camelCase contract."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class Availability(str, Enum):
    """Truthful availability states used throughout the contract."""

    LIVE = "live"
    STALE = "stale"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    UNAVAILABLE = "unavailable"


EvidenceKind = Literal[
    "event",
    "alert",
    "track",
    "detection",
    "recording",
    "statistics",
    "health",
]


class Freshness(ContextModel):
    """When a source was observed and whether it is safe to treat as current."""

    observed_at: datetime = Field(alias="observedAt")
    expires_at: Optional[datetime] = Field(default=None, alias="expiresAt")
    status: Availability
    reason: Optional[str] = None


class EvidenceRef(ContextModel):
    """A stable reference to data that supports a displayed item."""

    kind: EvidenceKind
    id: str
    camera_id: Optional[str] = Field(default=None, alias="cameraId")
    occurred_at: Optional[datetime] = Field(default=None, alias="occurredAt")
    recording_id: Optional[str] = Field(default=None, alias="recordingId")
    frame_timestamp: Optional[datetime] = Field(default=None, alias="frameTimestamp")
    label: str
    server_validated: bool = Field(default=False, alias="serverValidated")
    validated_at: Optional[datetime] = Field(default=None, alias="validatedAt")


class HealthCheck(ContextModel):
    """A source-specific health check, including its observation time."""

    name: Literal[
        "api",
        "database",
        "redis",
        "pipeline",
        "model",
        "event_stream",
        "persistence",
    ]
    status: Availability
    observed_at: datetime = Field(alias="observedAt")
    detail: Optional[str] = None


class OverallContext(ContextModel):
    status: Availability
    degraded_reasons: List[str] = Field(default_factory=list, alias="degradedReasons")
    checks: List[HealthCheck] = Field(default_factory=list)


class CameraItem(ContextModel):
    camera_id: str = Field(alias="cameraId")
    name: Optional[str] = None
    runtime: Availability
    last_frame_at: Optional[datetime] = Field(default=None, alias="lastFrameAt")
    freshness: Freshness


class CamerasContext(ContextModel):
    """Runtime camera counts; ``None`` means the runtime manager was unavailable."""

    total: Optional[int] = None
    total_configured: Optional[int] = Field(default=None, alias="totalConfigured")
    online: Optional[int] = None
    offline: Optional[int] = None
    stale: Optional[int] = None
    unavailable: Optional[int] = None
    items: List[CameraItem] = Field(default_factory=list)
    freshness: Freshness


class RiskAlertItem(ContextModel):
    alert_id: str = Field(alias="alertId")
    level: Optional[str] = None
    # Live APIState alert records do not yet carry acknowledgement state.
    acknowledged: Optional[bool] = None
    evidence: List[EvidenceRef] = Field(default_factory=list)
    freshness: Freshness


class AlertsContext(ContextModel):
    active_count: Optional[int] = Field(default=None, alias="activeCount")
    items: List[RiskAlertItem] = Field(default_factory=list)
    freshness: Freshness


class IncidentsCapability(ContextModel):
    capability: Availability
    reason: Optional[str] = None
    active_count: Optional[int] = Field(default=None, alias="activeCount")


class EventItem(ContextModel):
    event_id: str = Field(alias="eventId")
    risk_score: Optional[float] = Field(default=None, alias="riskScore")
    risk_level: Optional[str] = Field(default=None, alias="riskLevel")
    summary: str
    evidence: List[EvidenceRef] = Field(default_factory=list)
    freshness: Freshness


class TrackItem(ContextModel):
    track_id: str = Field(alias="trackId")
    camera_id: Optional[str] = Field(default=None, alias="cameraId")
    class_name: str = Field(alias="className")
    risk_score: Optional[float] = Field(default=None, alias="riskScore")
    verification_status: Optional[str] = Field(default=None, alias="verificationStatus")
    evidence: List[EvidenceRef] = Field(default_factory=list)
    freshness: Freshness


class DetectionSummary(ContextModel):
    recent_count: Optional[int] = Field(default=None, alias="recentCount")
    freshness: Freshness


class SemanticContext(ContextModel):
    capability: Availability
    mode: Optional[Literal["live_evidence"]] = None
    reason: Optional[str] = None
    active_query: Optional[str] = Field(default=None, alias="activeQuery")
    evidence: List[EvidenceRef] = Field(default_factory=list)
    freshness: Freshness


class PipelineStageContext(ContextModel):
    name: str
    status: Availability
    observed_at: datetime = Field(alias="observedAt")
    detail: Optional[str] = None


class PipelineContext(ContextModel):
    running: Optional[bool] = None
    stages: List[PipelineStageContext] = Field(default_factory=list)
    freshness: Freshness


class VoiceCapability(ContextModel):
    push_to_talk: Availability = Field(alias="pushToTalk")
    hands_free: Availability = Field(alias="handsFree")
    reason: Optional[str] = None


class AIContext(ContextModel):
    chat: Availability
    provider_configured: Optional[bool] = Field(default=None, alias="providerConfigured")
    evidence_grounding: Availability = Field(alias="evidenceGrounding")
    reason: Optional[str] = None
    voice: VoiceCapability


class IntelligenceSuggestion(ContextModel):
    suggestion_id: str = Field(alias="suggestionId")
    label: str
    reason: str
    evidence: List[EvidenceRef] = Field(default_factory=list)
    availability: Availability
    href: Optional[str] = None


class IntelligenceContext(ContextModel):
    """Version 1.0 contract consumed by the Phase 0 Intelligence page."""

    schema_version: Literal["1.0"] = Field(default="1.0", alias="schemaVersion")
    context_id: str = Field(alias="contextId")
    generated_at: datetime = Field(alias="generatedAt")
    refresh_after_seconds: int = Field(alias="refreshAfterSeconds", ge=1)
    overall: OverallContext
    cameras: CamerasContext
    alerts: AlertsContext
    incidents: IncidentsCapability
    events: List[EventItem] = Field(default_factory=list)
    tracks: List[TrackItem] = Field(default_factory=list)
    detections: DetectionSummary
    semantic: SemanticContext
    pipeline: PipelineContext
    ai: AIContext
    suggestions: List[IntelligenceSuggestion] = Field(default_factory=list)
