"""
AegisAI - Pipeline Startup

Factory that builds and wires the full AI processing pipeline.
Called during application startup to connect all stages.

Usage:
    from aegis.pipeline.startup import create_pipeline, get_pipeline

    # During app startup
    pipeline = create_pipeline()
    pipeline.start()

    # Get the running pipeline anywhere
    pipeline = get_pipeline()
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

from aegis.pipeline.stages import Pipeline

logger = logging.getLogger(__name__)

_pipeline: Optional[Pipeline] = None
_pipeline_lock = threading.Lock()


def create_pipeline(
    model_path: str = "yolo11n.pt",
    confidence: float = 0.5,
    device: str = "",
    auto_start: bool = False,
    warm_model: bool = False,
) -> Pipeline:
    """
    Build the full AI processing pipeline.

    Creates all stages and wires them together:
        DetectionStage → TrackingStage → RiskScoringStage → AlertingStage

    Args:
        model_path: Path to YOLO model weights
        confidence: Detection confidence threshold
        device: Compute device (empty string = auto)
        auto_start: Whether to start the pipeline immediately
        warm_model: Whether to load detector weights before returning. A
            failed warmup is surfaced in health without preventing the rest
            of the pipeline from starting.

    Returns:
        Configured Pipeline instance
    """
    global _pipeline

    from aegis.pipeline.detection import DetectionStage
    from aegis.pipeline.tracking import TrackingStage
    from aegis.pipeline.risk_scoring import RiskScoringStage
    from aegis.pipeline.alerting import AlertingStage

    pipeline = Pipeline()

    # Stage 1: YOLO Detection
    detection = DetectionStage(
        model_path=model_path,
        confidence=confidence,
        device=device,
        batch_size=1,
    )

    # Stage 2: Multi-Object Tracking + Analysis
    tracking = TrackingStage(batch_size=1)

    # Stage 3: Risk Scoring
    risk_scoring = RiskScoringStage(batch_size=1)

    # Stage 4: Alert Generation + Persistence
    alerting = AlertingStage(
        event_buffer_size=2000,
        high_risk_threshold=0.7,
        critical_risk_threshold=0.85,
    )

    pipeline.add_stage(detection)
    pipeline.add_stage(tracking)
    pipeline.add_stage(risk_scoring)
    pipeline.add_stage(alerting)

    if warm_model:
        try:
            detection.preload_model()
            logger.info("Detection model preloaded path=%s", model_path)
        except Exception as exc:
            logger.warning("Detection model preload failed (%s)", type(exc).__name__)

    with _pipeline_lock:
        _pipeline = pipeline

    logger.info(
        "Pipeline created stages=%d model=%s device=%s",
        len(pipeline._stages),
        model_path,
        device or "auto",
    )

    if auto_start:
        pipeline.start()

    return pipeline


def get_pipeline() -> Optional[Pipeline]:
    """Get the global pipeline instance (may be None if not started)."""
    return _pipeline


def get_alerting_stage():
    """Get the alerting stage for direct event/detection queries."""
    if _pipeline is None:
        return None
    for stage in _pipeline._stages:
        if stage.name == "alerting":
            return stage
    return None


def shutdown_pipeline() -> None:
    """Gracefully stop the pipeline."""
    global _pipeline
    if _pipeline:
        _pipeline.stop()
        _pipeline = None
        logger.info("Pipeline shutdown complete")
