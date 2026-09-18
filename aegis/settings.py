"""
AegisAI - Configuration via Pydantic BaseSettings

All configuration is driven by environment variables with sensible defaults.
No hardcoded paths. No platform-specific values.

Usage:
    from aegis.settings import get_settings
    settings = get_settings()
    print(settings.detection.model_path)
"""

from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DeviceType(str, Enum):
    """Supported compute devices for inference."""
    AUTO = "auto"
    CPU = "cpu"
    CUDA = "cuda"
    MPS = "mps"


# ---------------------------------------------------------------------------
# Sub-configurations (nested models)
# ---------------------------------------------------------------------------

class DetectionSettings(BaseSettings):
    """YOLO Detection Configuration."""

    model_path: str = Field(
        "yolo11n.pt",
        description="Path to YOLO model weights",
        validation_alias="AEGIS_DETECTION_MODEL_PATH",
    )
    confidence_threshold: float = Field(0.5, ge=0.0, le=1.0)
    nms_threshold: float = Field(0.45, ge=0.0, le=1.0)
    target_classes: Tuple[int, ...] = (0, 2, 3, 5, 7, 14, 15, 16, 34, 43, 76)
    image_size: int = Field(640, ge=320, le=1280)
    frame_skip: int = Field(1, ge=1)
    half_precision: bool = False

    # Weapon detection
    weapon_model_path: str = Field(
        default="models/weapon_detector.pt",
        description="Path to weapon detector weights. Set via AEGIS_WEAPON_MODEL_PATH.",
        validation_alias="AEGIS_WEAPON_MODEL_PATH",
    )
    weapon_confidence_threshold: float = Field(
        0.35,
        ge=0.0,
        le=1.0,
        validation_alias="AEGIS_WEAPON_CONFIDENCE_THRESHOLD",
    )
    weapon_classes: Tuple[int, ...] = (34, 43, 76)
    weapon_model_class_names: Dict[int, str] = Field(
        default={0: "knife", 1: "pistol"},
        validation_alias="AEGIS_WEAPON_CLASS_NAMES_JSON",
    )
    weapon_internal_class_ids: Dict[int, int] = Field(
        default={0: 1000, 1: 1001},
        validation_alias="AEGIS_WEAPON_INTERNAL_CLASS_IDS_JSON",
    )
    weapon_debug_enabled: bool = True

    # Animal classes for filtering false positives (COCO: bird, cat, dog)
    animal_classes: Tuple[int, ...] = (14, 15, 16)

    # Class name mapping for visualization
    class_names: Dict[int, str] = {
        0: "Person", 2: "Car", 3: "Motorcycle", 5: "Bus",
        7: "Truck", 14: "Bird", 15: "Cat", 16: "Dog",
        34: "Baseball Bat", 43: "Knife", 76: "Scissors",
    }

    model_config = {"env_prefix": "AEGIS_DETECTION_"}


class TrackingSettings(BaseSettings):
    """DeepSORT / ByteTrack Tracking Configuration."""

    max_age: int = 30
    n_init: int = 3
    max_iou_distance: float = 0.7
    max_cosine_distance: float = 0.3
    nn_budget: Optional[int] = 100
    embedder: str = "mobilenet"
    embedder_gpu: bool = True

    model_config = {"env_prefix": "AEGIS_TRACKING_"}


class VideoSettings(BaseSettings):
    """Video Processing Configuration."""

    output_codec: str = "mp4v"
    output_fps: Optional[float] = None
    display_window: bool = True
    window_name: str = "AegisAI - Perception Layer"
    resize_width: Optional[int] = None
    resize_height: Optional[int] = None

    model_config = {"env_prefix": "AEGIS_VIDEO_"}


class VehicleEnrichmentSettings(BaseSettings):
    """Optional, rate-limited vehicle enrichment configuration.

    This settings group deliberately uses the explicit environment names shown
    in the operator documentation. All expensive features are off by default.
    """

    enabled: bool = Field(False, validation_alias="VEHICLE_ENRICHMENT_ENABLED")
    plate_ocr_enabled: bool = Field(False, validation_alias="PLATE_OCR_ENABLED")
    plate_ocr_device: Literal["auto", "cpu", "gpu"] = Field("auto", validation_alias="PLATE_OCR_DEVICE")
    plate_ocr_model_dir: str = Field("", validation_alias="PLATE_OCR_MODEL_DIR")
    plate_detector_model_path: str = Field("", validation_alias="PLATE_DETECTOR_MODEL_PATH")
    vehicle_color_enabled: bool = Field(False, validation_alias="VEHICLE_COLOR_ENABLED")
    vehicle_make_model_enabled: bool = Field(False, validation_alias="VEHICLE_MAKE_MODEL_ENABLED")
    vehicle_make_model_model_path: str = Field("", validation_alias="VEHICLE_MAKE_MODEL_MODEL_PATH")
    vehicle_make_model_labels_path: str = Field("", validation_alias="VEHICLE_MAKE_MODEL_LABELS_PATH")
    vehicle_make_model_architecture: str = Field("", validation_alias="VEHICLE_MAKE_MODEL_ARCHITECTURE")
    interval_seconds: float = Field(default=1.5, ge=0.25, le=60.0, validation_alias="VEHICLE_ENRICHMENT_INTERVAL_SECONDS")
    max_enrichments_per_frame: int = Field(default=1, ge=1, le=8, validation_alias="VEHICLE_ENRICHMENT_MAX_ENRICHMENTS_PER_FRAME")
    tracker_state_ttl_seconds: float = Field(default=120.0, ge=10.0, le=3600.0, validation_alias="VEHICLE_ENRICHMENT_TRACKER_STATE_TTL_SECONDS")
    tracker_cache_limit: int = Field(default=500, ge=10, le=10_000, validation_alias="VEHICLE_ENRICHMENT_TRACKER_CACHE_LIMIT")
    min_crop_width: int = Field(default=160, ge=16, le=4096, validation_alias="VEHICLE_MIN_CROP_WIDTH")
    min_crop_height: int = Field(default=80, ge=16, le=4096, validation_alias="VEHICLE_MIN_CROP_HEIGHT")
    min_sharpness: float = Field(default=80.0, ge=0.0, le=100_000.0, validation_alias="VEHICLE_MIN_SHARPNESS")
    min_brightness: float = Field(default=35.0, ge=0.0, le=255.0, validation_alias="VEHICLE_MIN_BRIGHTNESS")
    evidence_deduplication_enabled: bool = Field(True, validation_alias="EVIDENCE_DEDUPLICATION_ENABLED")
    evidence_phash_max_distance: int = Field(default=8, ge=0, le=64, validation_alias="EVIDENCE_PHASH_MAX_DISTANCE")
    evidence_cache_limit: int = Field(default=500, ge=10, le=10_000, validation_alias="EVIDENCE_CACHE_LIMIT")
    evidence_retention_seconds: float = Field(default=180.0, ge=10.0, le=3600.0, validation_alias="EVIDENCE_RETENTION_SECONDS")
    inference_backend: Literal["torch", "tensorrt"] = Field("torch", validation_alias="INFERENCE_BACKEND")

    model_config = {
        "env_prefix": "",
        "env_file": ".env",
        "extra": "ignore",
        "populate_by_name": True,
    }


class VisualizationSettings(BaseSettings):
    """Visualization and Rendering Configuration."""

    bbox_thickness: int = 2
    font_scale: float = 0.6
    font_thickness: int = 2
    label_padding: int = 5
    show_confidence: bool = True
    show_class_name: bool = True
    show_track_id: bool = True

    class_colors: Dict[int, Tuple[int, int, int]] = {
        0: (0, 255, 128), 2: (255, 128, 0), 3: (0, 128, 255),
        5: (255, 0, 128), 7: (128, 255, 0), 14: (200, 200, 0),
        15: (0, 200, 200), 16: (200, 100, 50),
    }
    weapon_color: Tuple[int, int, int] = (0, 0, 255)
    default_color: Tuple[int, int, int] = (128, 128, 128)

    model_config = {"env_prefix": "AEGIS_VIS_"}


class AnalysisSettings(BaseSettings):
    """Phase 2 Analysis Layer Configuration."""

    enabled: bool = False
    history_window_size: int = 300
    min_history_for_analysis: int = 5
    stationary_speed_threshold: float = 2.0
    loitering_time_threshold: float = 5.0
    speed_change_threshold: float = 3.0
    direction_reversal_threshold: float = 2.356
    erratic_variance_threshold: float = 0.5
    running_speed_threshold: float = 15.0
    grid_cell_size: int = 100
    crowd_density_threshold: int = 5
    assumed_fps: float = 30.0
    max_active_tracks: int = 100

    model_config = {"env_prefix": "AEGIS_ANALYSIS_"}


class RiskSettings(BaseSettings):
    """Phase 3 Risk Intelligence Layer Configuration."""

    enabled: bool = False
    low_threshold: float = 0.25
    medium_threshold: float = 0.50
    high_threshold: float = 0.75
    weight_loitering: float = 0.25
    weight_speed_anomaly: float = 0.18
    weight_direction_change: float = 0.15
    weight_crowd_density: float = 0.12
    weight_zone: float = 0.15
    weight_erratic: float = 0.10
    escalation_rate: float = 0.02
    decay_rate: float = 0.01
    use_zones: bool = True
    use_temporal: bool = True

    model_config = {"env_prefix": "AEGIS_RISK_"}


class AlertSettings(BaseSettings):
    """Phase 4 Alert System Configuration."""

    enabled: bool = False
    min_level: str = "HIGH"
    cooldown_seconds: float = 30.0
    log_to_file: bool = True
    log_path: str = "data/output/alerts.log"

    model_config = {"env_prefix": "AEGIS_ALERT_"}


class APISettings(BaseSettings):
    """API Server Configuration."""

    enabled: bool = False
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8080, ge=1, le=65535)
    serve_dashboard: bool = True

    model_config = {"env_prefix": "AEGIS_API_"}


class SemanticSettings(BaseSettings):
    """Phase 5 Semantic Layer Configuration (Grounding DINO)."""

    enabled: bool = False
    model_name: str = "groundingdino"
    box_threshold: float = 0.35
    text_threshold: float = 0.25
    risk_threshold_trigger: float = 0.6
    cache_ttl_seconds: int = 60
    max_concurrent_requests: int = 2
    device_override: Optional[str] = None

    model_config = {"env_prefix": "AEGIS_SEMANTIC_"}


class DatabaseSettings(BaseSettings):
    """Database Persistence Configuration."""

    url: str = Field(
        default="sqlite:///data/aegis.db",
        description="Database URL. Set via DATABASE_URL env var.",
    )
    retention_days: int = 30
    snapshot_retention_days: int = 7
    auto_cleanup: bool = True

    model_config = {"env_prefix": "AEGIS_DB_", "env_mapping": {"url": "DATABASE_URL"}}

    @field_validator("url", mode="before")
    @classmethod
    def _resolve_database_url(cls, v: str) -> str:
        """Allow DATABASE_URL env to override AEGIS_DB_URL."""
        return os.getenv("DATABASE_URL", v)


class EdgeSettings(BaseSettings):
    """Edge Layer Configuration for hybrid edge/cloud architecture."""

    enabled: bool = True
    escalation_threshold: float = 0.4
    weapon_detected_score: float = 0.5
    weapon_person_coexist_score: float = 0.3
    weapon_person_overlap_score: float = 0.2
    behavioral_anomaly_score: float = 0.15
    max_event_queue_size: int = 100
    event_cooldown_seconds: float = 10.0
    frame_compression_quality: int = 85

    model_config = {"env_prefix": "AEGIS_EDGE_"}


class CloudSettings(BaseSettings):
    """Cloud Layer Configuration for GPU backend."""

    enabled: bool = False
    api_url: str = ""
    api_key: str = ""
    timeout_seconds: float = 5.0
    max_retries: int = 3
    max_queue_size: int = 100
    circuit_breaker_failures: int = 5
    circuit_breaker_reset_seconds: float = 60.0

    model_config = {"env_prefix": "AEGIS_CLOUD_"}


class ByteTrackSettings(BaseSettings):
    """ByteTrack Tracking Configuration (CPU-optimized)."""

    track_activation_threshold: float = 0.25
    lost_track_buffer: int = 30
    minimum_matching_threshold: float = 0.3
    frame_rate: int = 30

    model_config = {"env_prefix": "AEGIS_BYTETRACK_"}


class ProximityRiskSettings(BaseSettings):
    """Proximity Risk Engine Configuration."""

    enabled: bool = True
    weapon_coexist_score: float = 0.5
    weapon_overlap_score: float = 0.7
    stability_high_score: float = 0.85
    behavioral_boost: float = 0.1
    stability_window: int = 5
    decay_frames: int = 10
    escalation_threshold: float = 0.6
    iou_threshold: float = 0.05

    model_config = {"env_prefix": "AEGIS_PROXIMITY_"}


class GeminiSettings(BaseSettings):
    """Google Gemini LLM Configuration."""

    api_key: str = Field(default="", description="Gemini API key")
    model: str = "gemini-2.0-flash-exp"
    max_tokens: int = 2048
    temperature: float = 0.7
    timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0

    model_config = {"env_prefix": "GEMINI_"}


class GeminiLiveSettings(BaseSettings):
    """Server-only Gemini Live native-audio configuration.

    A session is enabled only when every required setting is present. The
    configured model and voice are verified when the Live connection opens,
    so an invalid provider-side value becomes an explicit capability error.
    """

    enabled: bool = False
    # These are current Gemini Live defaults. Operators can replace either
    # value through the corresponding GEMINI_LIVE_* environment variable.
    model: str = "gemini-3.1-flash-live-preview"
    # Kore is the established Aegis Live voice. This may be overridden with
    # GEMINI_LIVE_VOICE.
    voice: str = "Kore"
    # PCM is kept explicit at the gateway boundary.  Gemini Live accepts the
    # input rate in the MIME type; the browser needs the output rate to queue
    # native audio without guessing a format.
    input_sample_rate: int = Field(default=16_000, ge=8_000, le=48_000)
    output_sample_rate: int = Field(default=24_000, ge=8_000, le=48_000)
    session_ttl_seconds: int = Field(default=120, ge=30, le=900)
    max_session_seconds: int = Field(default=900, ge=60, le=900)
    tool_audit_retention_seconds: int = Field(default=3600, ge=0, le=86_400)
    transcript_retention_seconds: int = Field(default=0, ge=0, le=86_400)

    model_config = {"env_prefix": "GEMINI_LIVE_"}


class RedisSettings(BaseSettings):
    """Redis Configuration for event bus and pipeline messaging."""

    url: str = Field(default="redis://localhost:6379/0", description="Redis connection URL")
    max_connections: int = Field(default=20, ge=5, le=100, description="Connection pool size")

    # Stream settings for the AI pipeline
    stream_prefix: str = Field(default="aegis", description="Prefix for all Redis stream keys")
    stream_maxlen: int = Field(default=10000, description="Max entries per stream (trim)")
    consumer_group: str = Field(default="aegis-pipeline", description="Consumer group name")

    # Worker settings
    inference_workers: int = Field(default=2, ge=1, le=8, description="Number of inference worker processes")
    worker_batch_size: int = Field(default=4, ge=1, le=16, description="Frames per inference batch")
    worker_timeout_ms: int = Field(default=5000, ge=1000, le=30000, description="Worker read timeout (ms)")
    frame_ttl_seconds: int = Field(default=10, ge=1, le=60, description="Max age of a queued frame before drop")

    model_config = {"env_prefix": "REDIS_"}


# ---------------------------------------------------------------------------
# Master settings
# ---------------------------------------------------------------------------

class AegisSettings(BaseSettings):
    """
    Master Configuration — aggregates all sub-configurations.

    All values can be overridden via environment variables.
    Sub-configurations use prefixes (e.g., AEGIS_DETECTION_MODEL_PATH).

    Top-level env vars:
        AEGIS_DEBUG — enable debug mode
        AEGIS_API_KEY — API authentication key
        AEGIS_ALLOWED_ORIGINS — comma-separated CORS origins
        AEGIS_RATE_LIMIT — requests per window
        AEGIS_RATE_LIMIT_WINDOW — window in seconds
    """

    # Top-level settings
    debug: bool = Field(default=False, description="Debug mode")
    api_key: str = Field(default="", description="API authentication key")
    allowed_origins: str = Field(
        default="http://localhost:3000,http://localhost:8080",
        description="Comma-separated CORS origins",
    )
    rate_limit: int = Field(default=60, description="Rate limit (requests per window)")
    rate_limit_window: int = Field(default=60, description="Rate limit window (seconds)")

    # Device
    device: DeviceType = DeviceType.AUTO

    # Sub-configurations
    detection: DetectionSettings = Field(default_factory=DetectionSettings)
    tracking: TrackingSettings = Field(default_factory=TrackingSettings)
    video: VideoSettings = Field(default_factory=VideoSettings)
    vehicle_enrichment: VehicleEnrichmentSettings = Field(default_factory=VehicleEnrichmentSettings)
    visualization: VisualizationSettings = Field(default_factory=VisualizationSettings)
    analysis: AnalysisSettings = Field(default_factory=AnalysisSettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    alerts: AlertSettings = Field(default_factory=AlertSettings)
    api: APISettings = Field(default_factory=APISettings)
    semantic: SemanticSettings = Field(default_factory=SemanticSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    edge: EdgeSettings = Field(default_factory=EdgeSettings)
    cloud: CloudSettings = Field(default_factory=CloudSettings)
    bytetrack: ByteTrackSettings = Field(default_factory=ByteTrackSettings)
    proximity_risk: ProximityRiskSettings = Field(default_factory=ProximityRiskSettings)
    gemini: GeminiSettings = Field(default_factory=GeminiSettings)
    gemini_live: GeminiLiveSettings = Field(default_factory=GeminiLiveSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)

    model_config = {"env_prefix": "AEGIS_", "env_file": ".env", "extra": "ignore"}

    def get_device_string(self) -> str:
        """Resolve device string for model loading."""
        if self.device == DeviceType.AUTO:
            return ""
        return self.device.value

    def get_allowed_origins_list(self) -> List[str]:
        """Parse allowed origins into a list."""
        if not self.allowed_origins:
            return ["http://localhost:8080", "http://127.0.0.1:8080"]
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> AegisSettings:
    """Get the global settings singleton (cached)."""
    return AegisSettings()
