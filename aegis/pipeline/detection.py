"""
AegisAI - Detection Pipeline Stage

Wraps the YOLO detector as a pipeline stage. Reads frames from Redis,
runs inference, publishes detection results.

This stage owns the YOLO model instance and can be run in a separate
process for GPU isolation (Phase 1.1).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

from aegis.pipeline.stages import PipelineStage, Streams

logger = logging.getLogger(__name__)


class DetectionStage(PipelineStage):
    """
    YOLO detection pipeline stage.

    Reads frames from per-camera streams, runs inference, and publishes
    detection results with bounding boxes, class IDs, and confidence scores.

    The YOLO model is loaded lazily on first process() call to avoid
    importing ultralytics at import time.
    """

    def __init__(
        self,
        model_path: str = "yolo11n.pt",
        confidence: float = 0.5,
        device: str = "",
        **kwargs,
    ):
        super().__init__(
            name="detection",
            input_stream=Streams.FRAMES,
            output_stream=Streams.DETECTIONS,
            **kwargs,
        )
        self._model_path = model_path
        self._confidence = confidence
        self._device = device
        self._detector = None
        self._detector_lock = threading.Lock()
        self._model_load_error: Optional[str] = None

    def _get_detector(self):
        """Lazy-load the YOLO detector."""
        if self._detector is None:
            with self._detector_lock:
                if self._detector is None:
                    from config import DetectionConfig
                    from aegis.detection.yolo_detector import YOLODetector

                    # ``YOLODetector`` accepts the canonical DetectionConfig,
                    # not individual keyword arguments. Keeping the stage
                    # configuration explicit ensures the production pipeline
                    # loads the same weights and threshold it reports.
                    self._detector = YOLODetector(
                        detection_config=DetectionConfig(
                            model_path=self._model_path,
                            confidence_threshold=self._confidence,
                        ),
                    )
                    logger.info(
                        "Detection model loaded path=%s device=%s",
                        self._model_path,
                        self._device or "auto",
                    )
        return self._detector

    def preload_model(self) -> None:
        """Load the actual model weights before health is reported as live."""
        try:
            detector = self._get_detector()
            _ = detector.model
            self._model_load_error = None
        except Exception as exc:
            self._model_load_error = f"{type(exc).__name__}: {exc}"
            raise

    def process(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Run detection on a batch of frames.

        Input message format:
            {
                "camera_id": str,
                "frame_id": int,
                "frame_shape": [H, W, C],
                "timestamp": float,
                "metadata": dict (optional)
            }

        Note: Frame pixel data is NOT sent through Redis (too large).
        Instead, frames are stored in shared memory or a frame buffer,
        and the message contains only the reference (camera_id + frame_id).

        For now, this stage works with the existing FrameIngestionService
        as a thin wrapper. Full frame-over-Redis will be implemented when
        we add process isolation.
        """
        results = []
        detector = self._get_detector()

        for msg in messages:
            camera_id = msg.get("camera_id", "unknown")
            frame_id = msg.get("frame_id", 0)
            frame = msg.get("_frame")  # In-process frame reference

            if frame is None:
                logger.debug(
                    "Skipping frame without data camera_id=%s frame_id=%s",
                    camera_id,
                    frame_id,
                )
                continue

            try:
                start = time.monotonic()
                detections = detector.detect(frame)
                inference_ms = (time.monotonic() - start) * 1000

                det_list = []
                for det in detections:
                    det_list.append({
                        "bbox": list(getattr(det, "bbox", (0, 0, 0, 0))),
                        "confidence": float(getattr(det, "confidence", 0.0)),
                        "class_id": int(getattr(det, "class_id", 0)),
                        "class_name": str(getattr(det, "class_name", "unknown")),
                    })

                results.append({
                    "camera_id": camera_id,
                    "frame_id": frame_id,
                    "timestamp": msg.get("timestamp", time.time()),
                    "detections": det_list,
                    "detection_count": len(det_list),
                    "inference_ms": round(inference_ms, 2),
                    "_frame": frame,  # Pass frame reference downstream
                })

            except Exception as exc:
                logger.error(
                    "Detection failed camera_id=%s frame_id=%s: %s",
                    camera_id,
                    frame_id,
                    exc,
                )

        return results

    def get_model_info(self) -> Dict[str, Any]:
        """Return model metadata."""
        if self._detector is None:
            return {"loaded": False, "model_path": self._model_path}

        return {
            "loaded": True,
            "model_path": self._model_path,
            "confidence": self._confidence,
            "device": self._device or "auto",
        }
