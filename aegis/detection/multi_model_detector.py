"""
AegisAI multi-model detector.

Runs the existing person/object detector and the custom weapon detector on the
same frame, then returns one normalized Detection list for tracking.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import List, Optional

import numpy as np

from config import AegisConfig, DetectionConfig
from aegis.detection.weapon_detector import WeaponDetector
from aegis.detection.yolo_detector import Detection, YOLODetector

logger = logging.getLogger(__name__)


class MultiModelDetector:
    """Detector facade that preserves existing YOLO11n output and adds weapons."""

    def __init__(
        self,
        config: Optional[AegisConfig] = None,
        detection_config: Optional[DetectionConfig] = None,
        person_detector: Optional[YOLODetector] = None,
        weapon_detector: Optional[WeaponDetector] = None,
        debug: Optional[bool] = None,
    ):
        if config is not None:
            self._config = config.detection
        elif detection_config is not None:
            self._config = detection_config
        else:
            self._config = DetectionConfig()

        self.person_detector = person_detector or YOLODetector(config=config, detection_config=detection_config)
        self.weapon_detector = weapon_detector or WeaponDetector(config=config, detection_config=detection_config)
        self._debug = self._config.weapon_debug_enabled if debug is None else debug

    def detect(self, frame: np.ndarray) -> List[Detection]:
        person_detections = self.person_detector.detect(frame)
        weapon_detections = self.weapon_detector.detect(frame)
        detections = [*person_detections, *weapon_detections]

        if self._debug:
            self._print_debug(person_detections, weapon_detections)

        logger.debug(
            "MultiModelDetector detections total=%s person_object=%s weapon=%s",
            len(detections),
            len(person_detections),
            len(weapon_detections),
        )
        return detections

    def get_model_capabilities(self) -> dict:
        person_config = getattr(self.person_detector, "_config", self._config)
        person_names = dict(getattr(self.person_detector, "_class_names", person_config.CLASS_NAMES))
        person_classes = [
            person_names.get(class_id, f"class_{class_id}")
            for class_id in sorted(set(person_config.target_classes))
        ]
        weapon_capabilities = self.weapon_detector.get_capabilities()
        weapon_classes = list(weapon_capabilities["supported_classes"])

        return {
            "model_name": person_config.model_path,
            "supported_classes": [*person_classes, *weapon_classes],
            "weapon_detection_supported": bool(weapon_capabilities["weapon_detection_supported"]),
            "person_detector": {
                "model_name": person_config.model_path,
                "supported_classes": person_classes,
            },
            "weapon_detector": {
                "model_name": weapon_capabilities["model_name"],
                "supported_classes": weapon_classes,
                "internal_class_ids": weapon_capabilities["internal_class_ids"],
                "weapon_detection_supported": bool(weapon_capabilities["weapon_detection_supported"]),
            },
            "action_recognition_supported": False,
            "pose_estimation_supported": False,
            "semantic_verification_supported": False,
        }

    def _print_debug(self, person_detections: List[Detection], weapon_detections: List[Detection]) -> None:
        person_count = sum(1 for detection in person_detections if detection.is_person)
        print(f"Person: {person_count}")

        weapon_confidences: dict[str, list[float]] = defaultdict(list)
        for detection in weapon_detections:
            weapon_confidences[detection.class_name].append(float(detection.confidence))

        for class_name in self._config.weapon_model_class_names.values():
            confidences = weapon_confidences.get(class_name, [])
            display_name = class_name[:1].upper() + class_name[1:]
            if confidences:
                joined = ", ".join(f"{confidence:.2f}" for confidence in confidences)
                print(f"{display_name}: {len(confidences)} ({joined})")
            else:
                print(f"{display_name}: 0")

    def __repr__(self) -> str:
        return f"MultiModelDetector(person={self.person_detector!r}, weapon={self.weapon_detector!r})"
