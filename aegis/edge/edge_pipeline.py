"""
AegisAI - Edge Pipeline Coordinator (Phase 1)

Orchestrates the CPU-only edge processing pipeline:
    Frame → YOLO Detection → ByteTrack → Proximity Risk → [Cloud Escalation]

This is the main entry point for Phase 1 real-time processing.
Designed for Hugging Face Spaces (CPU) deployment.

Features:
- Single-frame processing (stateless per call, state in components)
- Event-based cloud escalation (only suspicious frames leave the edge)
- Modular design — swap detector/tracker/risk engine via interfaces
- Performance metrics tracking

Phase 1: Edge/CPU Intelligence
"""

import logging
import time
from typing import Optional

import cv2
import numpy as np

from config import AegisConfig
from aegis.edge.pipeline_types import PipelineResult
from aegis.edge.event_types import SuspiciousEvent

logger = logging.getLogger(__name__)


class EdgePipeline:
    """
    Phase 1 edge processing pipeline.

    Runs entirely on CPU with lightweight models.
    Pipeline: Frame → YOLO → ByteTrack → ProximityRisk → [CloudClient]

    Example:
        >>> pipeline = EdgePipeline()
        >>> pipeline.initialize()
        >>>
        >>> result = pipeline.process_frame(frame, frame_id=0, camera_id="cam1")
        >>> print(f"Risk: {result.risk_level}, Tracks: {result.track_count}")
        >>>
        >>> pipeline.shutdown()
    """

    def __init__(self, config: Optional[AegisConfig] = None):
        """
        Initialize edge pipeline with configuration.

        Args:
            config: AegisConfig instance. Uses defaults if not provided.
        """
        self._config = config or AegisConfig()

        # Components (lazy-loaded)
        self._detector = None
        self._tracker = None
        self._risk_engine = None
        self._cloud_client = None
        self._initialized = False

        # Statistics
        self._frames_processed = 0
        self._total_detections = 0
        self._total_escalations = 0
        self._avg_latency_ms = 0.0

        logger.info("EdgePipeline created (components will lazy-load)")

    def initialize(self) -> None:
        """
        Eagerly initialize all pipeline components.
        Call this before processing to avoid first-frame latency.
        """
        logger.info("Initializing edge pipeline components...")
        _ = self._get_detector()
        _ = self._get_tracker()
        _ = self._get_risk_engine()
        self._initialized = True
        logger.info("Edge pipeline fully initialized")

    def _get_detector(self):
        """Lazy-load YOLO detector."""
        if self._detector is None:
            from aegis.detection.yolo_detector import YOLODetector
            self._detector = YOLODetector(config=self._config)
            self._detector.warmup()
            logger.info("YOLO detector loaded and warmed up")
        return self._detector

    def _get_tracker(self):
        """Lazy-load ByteTrack tracker."""
        if self._tracker is None:
            from aegis.tracking.bytetrack_tracker import ByteTrackTracker
            self._tracker = ByteTrackTracker(config=self._config)
            logger.info("ByteTrack tracker loaded")
        return self._tracker

    def _get_risk_engine(self):
        """Lazy-load proximity risk engine."""
        if self._risk_engine is None:
            from aegis.risk.proximity_risk import ProximityRiskEngine
            self._risk_engine = ProximityRiskEngine(config=self._config)
            logger.info("ProximityRiskEngine loaded")
        return self._risk_engine

    def _get_cloud_client(self):
        """Lazy-load cloud client (only when needed for escalation)."""
        if self._cloud_client is None:
            try:
                from aegis.cloud.cloud_client import CloudClient
                self._cloud_client = CloudClient(config=self._config)
                if self._cloud_client.is_enabled:
                    self._cloud_client.start()
                    logger.info("CloudClient loaded and started")
                else:
                    logger.info("CloudClient disabled — no cloud escalation")
            except Exception as e:
                logger.warning(f"CloudClient not available: {e}")
        return self._cloud_client

    def process_frame(
        self,
        frame: np.ndarray,
        frame_id: int = 0,
        camera_id: str = "default",
    ) -> PipelineResult:
        """
        Process a single frame through the full edge pipeline.

        Pipeline stages:
            1. YOLO Detection (nano model, CPU)
            2. ByteTrack Tracking (IoU-based, CPU)
            3. Proximity Risk Assessment (rule-based)
            4. Cloud Escalation (event-based, only if suspicious)

        Args:
            frame: Input video frame (BGR numpy array)
            frame_id: Frame sequence number
            camera_id: Camera identifier

        Returns:
            PipelineResult with detections, tracks, and risk assessment
        """
        start = time.time()

        # ── Stage 1: Detection ──
        detector = self._get_detector()
        detections = detector.detect(frame)
        self._total_detections += len(detections)

        # ── Stage 2: Tracking ──
        tracker = self._get_tracker()
        tracks = tracker.update(detections, frame)

        # ── Stage 3: Risk Assessment ──
        risk_engine = self._get_risk_engine()
        risk_assessment = risk_engine.assess(tracks, frame_id)

        # ── Stage 4: Cloud Escalation (event-based) ──
        if risk_assessment.should_escalate:
            self._escalate_to_cloud(frame, risk_assessment, camera_id)

        # ── Build Result ──
        elapsed_ms = (time.time() - start) * 1000
        self._frames_processed += 1

        # Running average latency
        n = self._frames_processed
        self._avg_latency_ms = (self._avg_latency_ms * (n - 1) + elapsed_ms) / n

        result = PipelineResult(
            detections=detections,
            tracks=tracks,
            risk_assessment=risk_assessment,
            frame_id=frame_id,
            camera_id=camera_id,
            processing_time_ms=elapsed_ms,
        )

        if risk_assessment.risk_level in ("HIGH", "CRITICAL"):
            logger.info(
                f"Frame {frame_id} | {risk_assessment.risk_level} "
                f"({risk_assessment.risk_score:.2f}) | "
                f"triggers={risk_assessment.triggers} | "
                f"{elapsed_ms:.0f}ms"
            )

        return result

    def _escalate_to_cloud(
        self,
        frame: np.ndarray,
        risk_assessment,
        camera_id: str,
    ) -> None:
        """Send suspicious event to cloud for deep analysis."""
        cloud = self._get_cloud_client()
        if cloud is None or not cloud.is_enabled:
            return

        try:
            # Compress frame for transmission
            quality = 85
            if hasattr(self._config, 'edge'):
                quality = self._config.edge.frame_compression_quality

            encode_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
            _, jpeg_buffer = cv2.imencode('.jpg', frame, encode_params)
            frame_jpeg = jpeg_buffer.tobytes()

            h, w = frame.shape[:2]

            event = SuspiciousEvent(
                camera_id=camera_id,
                frame_jpeg=frame_jpeg,
                tracks=risk_assessment.track_summaries,
                edge_risk_score=risk_assessment.risk_score,
                triggers=risk_assessment.triggers,
                frame_id=risk_assessment.frame_id,
                frame_width=w,
                frame_height=h,
            )

            cloud.enqueue_event(event)
            self._total_escalations += 1

            logger.debug(
                f"Escalated event {event.event_id} to cloud | "
                f"score={risk_assessment.risk_score:.2f}"
            )

        except Exception as e:
            logger.error(f"Cloud escalation error: {e}")

    def get_stats(self) -> dict:
        """Get pipeline processing statistics."""
        stats = {
            "frames_processed": self._frames_processed,
            "total_detections": self._total_detections,
            "total_escalations": self._total_escalations,
            "avg_latency_ms": round(self._avg_latency_ms, 1),
            "initialized": self._initialized,
        }

        # Add component stats
        if self._risk_engine:
            stats["risk_engine"] = self._risk_engine.get_stats()
        if self._cloud_client:
            stats["cloud_client"] = self._cloud_client.get_stats()

        return stats

    def shutdown(self) -> None:
        """Gracefully shutdown all pipeline components."""
        if self._cloud_client:
            self._cloud_client.stop()
        logger.info(
            f"EdgePipeline shutdown | "
            f"frames={self._frames_processed}, "
            f"escalations={self._total_escalations}, "
            f"avg_latency={self._avg_latency_ms:.1f}ms"
        )

    def __enter__(self):
        self.initialize()
        return self

    def __exit__(self, *args):
        self.shutdown()

    def __repr__(self) -> str:
        return (
            f"EdgePipeline(initialized={self._initialized}, "
            f"frames={self._frames_processed}, "
            f"avg_ms={self._avg_latency_ms:.1f})"
        )
