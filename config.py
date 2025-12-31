"""
AegisAI - Smart City Risk Intelligence System
Configuration Management Module

This module centralizes all configuration parameters for AegisAI.
Covers Phase 1 (Perception) and Phase 2 (Analysis) configurations.
Designed for production deployment with environment-aware settings.
"""


from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from enum import Enum


class DeviceType(Enum):
    """Supported compute devices for inference."""
    AUTO = "auto"
    CPU = "cpu"
    CUDA = "cuda"
    MPS = "mps"  # Apple Silicon


@dataclass(frozen=True)
class DetectionConfig:
    """
    YOLOv8 Detection Configuration.
    
    Attributes:
        model_path: Path to YOLO model weights (default: yolov8n for speed)
        confidence_threshold: Minimum confidence for valid detections
        nms_threshold: Non-Maximum Suppression IoU threshold
        target_classes: COCO class IDs to detect
            - 0: person
            - 2: car
            - 3: motorcycle
            - 5: bus
            - 7: truck
        image_size: Input image size for inference
        frame_skip: Process every Nth frame (1=all, 2=every other, etc.)
        half_precision: Use FP16 inference (faster on GPU)
    """
    model_path: str = "yolov8n.pt"
    confidence_threshold: float = 0.5
    nms_threshold: float = 0.45
    target_classes: Tuple[int, ...] = (0, 2, 3, 5, 7)
    image_size: int = 640
    frame_skip: int = 1  # Process every frame by default
    half_precision: bool = True  # Use FP16 for faster inference
    
    # Class name mapping for visualization
    CLASS_NAMES: dict = field(default_factory=lambda: {
        0: "Person",
        2: "Car",
        3: "Motorcycle",
        5: "Bus",
        7: "Truck"
    })



@dataclass(frozen=True)
class TrackingConfig:
    """
    DeepSORT Tracking Configuration.
    
    Attributes:
        max_age: Maximum frames to keep a track without detections
        n_init: Minimum detections before track is confirmed
        max_iou_distance: Maximum IoU distance for association
        max_cosine_distance: Maximum cosine distance for appearance matching
        nn_budget: Maximum size of appearance feature gallery
        embedder: Feature extractor model for appearance
        embedder_gpu: Whether to use GPU for embedder
    """
    max_age: int = 30
    n_init: int = 3
    max_iou_distance: float = 0.7
    max_cosine_distance: float = 0.3
    nn_budget: Optional[int] = 100
    embedder: str = "mobilenet"
    embedder_gpu: bool = True


@dataclass(frozen=True)
class VideoConfig:
    """
    Video Processing Configuration.
    
    Attributes:
        output_codec: FourCC codec for output video
        output_fps: Output video framerate (None = match source)
        display_window: Whether to show live preview window
        window_name: Name of the preview window
        resize_width: Resize frame width for processing (None = original)
        resize_height: Resize frame height for processing (None = original)
    """
    output_codec: str = "mp4v"
    output_fps: Optional[float] = None
    display_window: bool = True
    window_name: str = "AegisAI - Perception Layer"
    resize_width: Optional[int] = None
    resize_height: Optional[int] = None


@dataclass(frozen=True)
class VisualizationConfig:
    """
    Visualization and Rendering Configuration.
    
    Attributes:
        bbox_thickness: Bounding box line thickness in pixels
        font_scale: Text size multiplier
        font_thickness: Text stroke thickness
        label_padding: Padding around label text
        show_confidence: Whether to display confidence scores
        show_class_name: Whether to display class names
        show_track_id: Whether to display track IDs
    """
    bbox_thickness: int = 2
    font_scale: float = 0.6
    font_thickness: int = 2
    label_padding: int = 5
    show_confidence: bool = True
    show_class_name: bool = True
    show_track_id: bool = True
    
    # Color palette for different classes (BGR format)
    # Designed for visual distinction and accessibility
    CLASS_COLORS: dict = field(default_factory=lambda: {
        0: (0, 255, 128),    # Person: Green
        2: (255, 128, 0),    # Car: Blue
        3: (0, 128, 255),    # Motorcycle: Orange
        5: (255, 0, 128),    # Bus: Purple
        7: (128, 255, 0),    # Truck: Cyan
    })
    
    # Default color for unknown classes
    DEFAULT_COLOR: Tuple[int, int, int] = (128, 128, 128)


@dataclass(frozen=True)
class AnalysisConfig:
    """
    Phase 2 Analysis Layer Configuration.
    
    Attributes:
        enabled: Whether analysis is enabled
        history_window_size: Frames to keep per track
        min_history_for_analysis: Min frames before computing metrics
        stationary_speed_threshold: Speed below this is stationary (px/frame)
        loitering_time_threshold: Seconds stationary to trigger loitering
        speed_change_threshold: Multiplier for sudden speed change
        direction_reversal_threshold: Radians for direction reversal (~135°)
        erratic_variance_threshold: Circular variance for erratic detection
        running_speed_threshold: Speed to consider as running (px/frame)
        grid_cell_size: Density grid cell size in pixels
        crowd_density_threshold: Objects per cell for "crowded"
        assumed_fps: Frame rate for time calculations
    """
    enabled: bool = False
    history_window_size: int = 300  # ~10 seconds at 30fps (optimized)
    min_history_for_analysis: int = 5
    stationary_speed_threshold: float = 2.0
    loitering_time_threshold: float = 5.0
    speed_change_threshold: float = 3.0
    direction_reversal_threshold: float = 2.356  # ~135 degrees
    erratic_variance_threshold: float = 0.5
    running_speed_threshold: float = 15.0
    grid_cell_size: int = 100
    crowd_density_threshold: int = 5
    assumed_fps: float = 30.0
    max_active_tracks: int = 100  # Limit concurrent tracks for performance



@dataclass(frozen=True)
class RiskConfig:
    """
    Phase 3 Risk Intelligence Layer Configuration.
    
    Attributes:
        enabled: Whether risk scoring is enabled
        low_threshold: Score threshold for LOW level
        medium_threshold: Score threshold for MEDIUM level
        high_threshold: Score threshold for HIGH level
        weight_loitering: Weight for loitering signal
        weight_speed_anomaly: Weight for speed changes
        weight_direction_change: Weight for direction reversals
        weight_crowd_density: Weight for crowd density
        weight_zone: Weight for zone context
        weight_erratic: Weight for erratic motion
        escalation_rate: Temporal risk increase rate
        decay_rate: Temporal risk decrease rate
        use_zones: Enable zone-based weighting
        use_temporal: Enable temporal adjustment
    """
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


@dataclass(frozen=True)
class AlertConfig:
    """
    Phase 4 Alert System Configuration.
    
    Attributes:
        enabled: Whether alerting is enabled
        min_level: Minimum risk level to trigger (HIGH, CRITICAL)
        cooldown_seconds: Per-track cooldown period
        log_to_file: Write alerts to file
        log_path: Path to alert log file
    """
    enabled: bool = False
    min_level: str = "HIGH"
    cooldown_seconds: float = 30.0
    log_to_file: bool = True
    log_path: str = "data/output/alerts.log"


@dataclass(frozen=True)
class APIConfig:
    """
    Phase 4 API Server Configuration.
    
    Attributes:
        enabled: Whether API server is enabled
        host: Server host address
        port: Server port
        serve_dashboard: Serve dashboard files
    """
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8080
    serve_dashboard: bool = True


@dataclass(frozen=True)
class SemanticConfig:
    """
    Phase 5 Semantic Layer Configuration (Grounding DINO).
    
    Enables language-guided semantic detection for scene understanding.
    DINO runs only on-demand (trigger-based) to preserve real-time performance.
    
    Attributes:
        enabled: Whether semantic layer is enabled
        model_name: Grounding DINO model variant
        box_threshold: Minimum confidence for bounding box detection
        text_threshold: Minimum confidence for text-phrase matching
        risk_threshold_trigger: Risk score above which to auto-trigger DINO
        cache_ttl_seconds: Time-to-live for prompt result cache
        max_concurrent_requests: Maximum parallel DINO inference requests
        device_override: Force specific device (None = auto GPU-first)
    """
    enabled: bool = False
    model_name: str = "groundingdino"
    box_threshold: float = 0.35
    text_threshold: float = 0.25
    risk_threshold_trigger: float = 0.6
    cache_ttl_seconds: int = 60
    max_concurrent_requests: int = 2
    device_override: Optional[str] = None  # None = auto (GPU-first, CPU fallback)


@dataclass(frozen=True)
class DatabaseConfig:
    """
    Database Persistence Configuration.
    
    Supports SQLite (default) and PostgreSQL for production.
    
    Attributes:
        enabled: Whether database persistence is enabled
        url: Database connection URL (overridable via DATABASE_URL env)
        retention_days: Days to keep events/alerts before cleanup
        snapshot_retention_days: Days to keep track snapshots
        auto_cleanup: Whether to auto-cleanup old records on startup
    """
    enabled: bool = True
    url: str = "sqlite:///data/aegis.db"
    retention_days: int = 30
    snapshot_retention_days: int = 7
    auto_cleanup: bool = True


@dataclass
class AegisConfig:
    """
    Master Configuration Container.
    
    Aggregates all sub-configurations for easy access and management.
    This is the primary configuration object passed throughout the system.
    
    Phase 1: detection, tracking, video, visualization
    Phase 2: analysis
    Phase 3: risk
    Phase 4: alerts, api
    Phase 5: semantic (Grounding DINO)
    """
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    tracking: TrackingConfig = field(default_factory=TrackingConfig)
    video: VideoConfig = field(default_factory=VideoConfig)
    visualization: VisualizationConfig = field(default_factory=VisualizationConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    alerts: AlertConfig = field(default_factory=AlertConfig)
    api: APIConfig = field(default_factory=APIConfig)
    semantic: SemanticConfig = field(default_factory=SemanticConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    device: DeviceType = DeviceType.AUTO
    
    def get_device_string(self) -> str:
        """
        Resolve device string for model loading.
        
        Returns:
            Device string compatible with PyTorch/Ultralytics
        """
        if self.device == DeviceType.AUTO:
            # Let the framework auto-detect best available device
            return ""
        return self.device.value


# Default configuration instance for convenience
DEFAULT_CONFIG = AegisConfig()


def load_config(config_path: Optional[str] = None) -> AegisConfig:
    """
    Load configuration from file or return defaults.
    
    Args:
        config_path: Optional path to YAML/JSON config file
        
    Returns:
        AegisConfig instance with loaded or default values
        
    Note:
        Future enhancement: Add YAML/JSON file loading support
        for deployment-specific configurations.
    """
    # TODO: Implement file-based configuration loading for Phase 2+
    if config_path:
        raise NotImplementedError(
            "File-based configuration loading will be implemented in Phase 2. "
            "Currently using default configuration."
        )
    return DEFAULT_CONFIG
