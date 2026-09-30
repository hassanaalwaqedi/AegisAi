"""Offline, prompted YOLOE threat-candidate detector.

The runtime uses model-bound, precomputed prompt embeddings. Ultralytics binds
those saved tensors through ``load_prompt_embeddings()`` during startup; that
method may internally call ``set_classes(names, embeddings)``, but it does not
create text embeddings or download a tokenizer/text encoder.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

import numpy as np
from ultralytics import YOLOE

from config import AegisConfig, DetectionConfig
from aegis.detection.yolo_detector import Detection

logger = logging.getLogger(__name__)


class YOLOEThreatDetector:
    """Emit open-vocabulary threat *candidates*, never risk decisions."""

    def __init__(
        self,
        config: Optional[AegisConfig] = None,
        detection_config: Optional[DetectionConfig] = None,
    ):
        if config is not None:
            self._config = config.detection
            self._device = config.get_device_string()
        elif detection_config is not None:
            self._config = detection_config
            self._device = ""
        else:
            self._config = DetectionConfig()
            self._device = ""

        self._model: Optional[YOLOE] = None
        self._model_path = str(self._config.threat_model_path)
        self._embeddings_path = str(self._config.threat_prompt_embeddings_path)
        self._prompts = tuple(self._config.threat_classes)
        self._enabled = bool(self._config.threat_detector_enabled)
        self._disabled_reason: Optional[str] = None if self._enabled else "Threat detector disabled by configuration"
        self._last_masks = None

        logger.info(
            "YOLOEThreatDetector initialized enabled=%s model=%s prompts=%s",
            self._enabled,
            self._model_path,
            len(self._prompts),
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def model(self) -> YOLOE:
        if not self._enabled:
            raise RuntimeError(self._disabled_reason or "Threat detector disabled")
        if self._model is None:
            model_path = Path(self._model_path)
            embeddings_path = Path(self._embeddings_path)
            if not model_path.is_file():
                self._disabled_reason = f"YOLOE threat checkpoint is unavailable: {model_path}"
                raise FileNotFoundError(self._disabled_reason)
            if not embeddings_path.is_file():
                self._disabled_reason = f"YOLOE prompt embeddings are unavailable: {embeddings_path}"
                raise FileNotFoundError(self._disabled_reason)
            try:
                model = YOLOE(str(model_path))
                # Offline-only: this binds precomputed tensors. In the
                # installed Ultralytics version it internally delegates to
                # set_classes(names, embeddings), without initializing the
                # text encoder or contacting the network.
                model.load_prompt_embeddings(str(embeddings_path))
                names = tuple(model.names.values()) if isinstance(model.names, dict) else tuple(model.names)
                if names != self._prompts:
                    raise ValueError("YOLOE prompt embedding classes do not match configured threat classes")
                self._model = model
                self._disabled_reason = None
                logger.info("Loaded offline YOLOE threat model: %s", model_path)
            except Exception as exc:
                self._disabled_reason = f"{type(exc).__name__}: {exc}"
                raise
        return self._model

    def preload(self) -> None:
        if self._enabled:
            _ = self.model

    def detect(self, frame: np.ndarray, confidence_threshold: Optional[float] = None) -> List[Detection]:
        if not self._enabled or self._disabled_reason:
            return []
        try:
            prediction_args = {
                "source": frame,
                "conf": (self._config.threat_confidence_threshold if confidence_threshold is None else confidence_threshold),
                "iou": self._config.nms_threshold,
                "imgsz": self._config.image_size,
                "device": self._device or None,
                "verbose": False,
            }
            if getattr(self._config, "half_precision", False):
                prediction_args["half"] = True
            results = self.model.predict(**prediction_args)
        except Exception as exc:
            self._disabled_reason = f"{type(exc).__name__}: {exc}"
            logger.warning("YOLOE threat detection disabled: %s", self._disabled_reason)
            return []

        detections: List[Detection] = []
        self._last_masks = []
        for result in results:
            if result.masks is not None:
                self._last_masks.append(result.masks)
            if result.boxes is None:
                continue
            for index in range(len(result.boxes)):
                source_class_id = int(result.boxes.cls[index].cpu().numpy())
                if source_class_id not in range(len(self._prompts)):
                    continue
                x1, y1, x2, y2 = map(int, result.boxes.xyxy[index].cpu().numpy())
                detections.append(
                    Detection(
                        bbox=(x1, y1, x2, y2),
                        confidence=float(result.boxes.conf[index].cpu().numpy()),
                        class_id=2000 + source_class_id,
                        class_name=self._prompts[source_class_id],
                        object_category="threat_candidate",
                        # Phase 4 does not alter risk or person-weapon
                        # association: candidates are evidence only.
                        is_weapon=False,
                        is_person=False,
                        is_vehicle=False,
                        is_animal=False,
                        model_source=self._model_path,
                        source_class_id=source_class_id,
                        detector="threat_yoloe",
                        evidence_type="threat_candidate",
                    )
                )
        return detections

    def get_last_masks(self):
        """Keep masks internally available for a later fusion phase."""
        return self._last_masks

    def get_capabilities(self) -> dict:
        model_path = Path(self._model_path)
        embeddings_path = Path(self._embeddings_path)
        available = self._enabled and model_path.is_file() and embeddings_path.is_file() and self._disabled_reason is None
        return {
            "threat_detection_supported": available,
            "enabled": self._enabled,
            "supported_classes": list(self._prompts),
            "runtime": self.get_runtime_metadata(),
        }

    def get_runtime_metadata(self) -> dict:
        model_path = Path(self._model_path)
        embeddings_path = Path(self._embeddings_path)
        metadata = {
            "backend": "ultralytics-yoloe",
            "configured": self._enabled,
            "configured_path": self._model_path,
            "resolved_path": str(model_path.resolve()),
            "model": model_path.name,
            "ready": False,
            "task": None,
            "class_count": len(self._prompts),
            "classes": list(self._prompts),
            "device": None,
            "prompt_mode": "precomputed_text_embeddings",
            "prompt_embeddings_path": self._embeddings_path,
            "prompt_embeddings_ready": embeddings_path.is_file(),
            "segmentation_available": True,
            "frame_skip": int(self._config.threat_frame_skip),
            "error": self._disabled_reason,
        }
        if self._model is None:
            if self._enabled and not model_path.is_file() and metadata["error"] is None:
                metadata["error"] = f"YOLOE threat checkpoint is unavailable: {model_path}"
            elif self._enabled and not embeddings_path.is_file() and metadata["error"] is None:
                metadata["error"] = f"YOLOE prompt embeddings are unavailable: {embeddings_path}"
            return metadata
        model = self._model
        metadata.update({
            "resolved_path": str(Path(getattr(model, "ckpt_path", model_path)).resolve()),
            "model": Path(getattr(model, "ckpt_path", model_path)).name,
            "ready": True,
            "task": getattr(model, "task", None),
            "device": str(getattr(model, "device", self._device or "auto")),
            "error": None,
        })
        return metadata
