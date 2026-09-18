"""
AegisAI custom weapon detector.

Runs the trained knife/pistol YOLO checkpoint and normalizes its output into the
same Detection objects used by the rest of the perception pipeline.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

import numpy as np
from ultralytics import YOLO

from config import AegisConfig, DetectionConfig
from aegis.detection.yolo_detector import Detection

logger = logging.getLogger(__name__)


class WeaponDetector:
    """YOLO wrapper for custom knife/pistol detection."""

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

        self._model: Optional[YOLO] = None
        self._model_path = self._config.weapon_model_path
        self._class_names = dict(self._config.weapon_model_class_names)
        self._internal_class_ids = dict(self._config.weapon_internal_class_ids)
        self._disabled_reason: Optional[str] = None
        self._class_mapping_validated = False

        missing_internal_ids = set(self._class_names) - set(self._internal_class_ids)
        if missing_internal_ids:
            self._disabled_reason = (
                "Missing internal IDs for custom weapon classes: "
                + ", ".join(str(class_id) for class_id in sorted(missing_internal_ids))
            )

        logger.info(
            "WeaponDetector initialized with model=%s confidence=%.2f classes=%s",
            self._model_path,
            self._config.weapon_confidence_threshold,
            self._class_names,
        )

    @property
    def model(self) -> YOLO:
        if self._model is None:
            path = Path(self._model_path)
            if not path.exists():
                raise FileNotFoundError(f"Weapon model was not found: {self._model_path}")
            logger.info("Loading weapon YOLO model: %s", self._model_path)
            try:
                model = YOLO(str(path))
                self._validate_class_mapping(model)
                self._model = model
            except Exception as exc:
                self._disabled_reason = str(exc)
                raise
            if hasattr(model, "device"):
                logger.info("Weapon model loaded on device: %s", model.device)
        return self._model

    def _validate_class_mapping(self, model: YOLO) -> None:
        raw_names = getattr(model, "names", None)
        if isinstance(raw_names, (list, tuple)):
            actual_names = {index: str(name) for index, name in enumerate(raw_names)}
        elif isinstance(raw_names, dict):
            actual_names = {int(index): str(name) for index, name in raw_names.items()}
        else:
            raise ValueError("Custom weapon weights do not expose a class-name mapping")

        mismatches = []
        for class_id, expected_name in self._class_names.items():
            actual_name = actual_names.get(int(class_id))
            if actual_name is None or self._normalize_label(actual_name) != self._normalize_label(expected_name):
                mismatches.append(
                    f"{class_id}: expected {expected_name!r}, model has {actual_name!r}"
                )
        if mismatches:
            raise ValueError("Custom weapon class mapping mismatch: " + "; ".join(mismatches))
        self._class_mapping_validated = True

    @staticmethod
    def _normalize_label(value: str) -> str:
        return " ".join(str(value).strip().lower().replace("_", " ").split())

    def detect(self, frame: np.ndarray, confidence_threshold: Optional[float] = None) -> List[Detection]:
        if self._disabled_reason:
            return []

        conf_thresh = self._config.weapon_confidence_threshold if confidence_threshold is None else confidence_threshold

        try:
            results = self.model.predict(
                source=frame,
                conf=conf_thresh,
                iou=self._config.nms_threshold,
                classes=list(self._class_names.keys()),
                imgsz=self._config.image_size,
                device=self._device if self._device else None,
                half=getattr(self._config, "half_precision", False),
                verbose=False,
            )
        except Exception as exc:
            self._disabled_reason = str(exc)
            logger.warning("Weapon detection disabled: %s", exc)
            return []

        detections: List[Detection] = []
        for result in results:
            if result.boxes is None or len(result.boxes) == 0:
                continue

            boxes = result.boxes
            for i in range(len(boxes)):
                source_class_id = int(boxes.cls[i].cpu().numpy())
                if source_class_id not in self._class_names:
                    continue

                xyxy = boxes.xyxy[i].cpu().numpy()
                x1, y1, x2, y2 = map(int, xyxy)
                confidence = float(boxes.conf[i].cpu().numpy())
                class_name = self._class_names[source_class_id]
                internal_class_id = int(self._internal_class_ids[source_class_id])

                detections.append(
                    Detection(
                        bbox=(x1, y1, x2, y2),
                        confidence=confidence,
                        class_id=internal_class_id,
                        class_name=class_name,
                        object_category="weapon",
                        is_weapon=True,
                        is_person=False,
                        is_vehicle=False,
                        is_animal=False,
                        model_source=self._model_path,
                        source_class_id=source_class_id,
                    )
                )

        logger.debug("WeaponDetector detected %s weapon objects", len(detections))
        return detections

    def get_capabilities(self) -> dict:
        model_exists = Path(self._model_path).is_file()
        available = model_exists and self._disabled_reason is None
        unavailable_reason = self._disabled_reason or (
            None if model_exists else f"Weapon detector weights are unavailable: {self._model_path}"
        )
        return {
            "model_name": self._model_path,
            "supported_classes": list(self._class_names.values()),
            "internal_class_ids": {
                name: int(self._internal_class_ids[source_id])
                for source_id, name in self._class_names.items()
            },
            "weapon_detection_supported": available,
            "disabled_reason": unavailable_reason,
            "class_mapping_validated": self._class_mapping_validated,
            "validation_status": (
                "unavailable"
                if not available
                else "validated"
                if self._class_mapping_validated
                else "configured_not_loaded"
            ),
        }

    def __repr__(self) -> str:
        return f"WeaponDetector(model={self._model_path}, classes={self._class_names})"
