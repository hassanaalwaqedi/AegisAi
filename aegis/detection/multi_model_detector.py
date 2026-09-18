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
        detections = self._merge_detections(person_detections, weapon_detections)

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
        configured_names = getattr(person_config, "CLASS_NAMES", getattr(person_config, "class_names", {}))
        person_names = dict(getattr(self.person_detector, "_class_names", configured_names))
        if hasattr(self.person_detector, "get_capabilities"):
            base_capabilities = self.person_detector.get_capabilities()
            base_available = bool(base_capabilities.get("detector_available", False))
            base_classes = list(base_capabilities["supported_classes"]) if base_available else []
            base_weapon_classes = list(base_capabilities["weapon_classes"]) if base_available else []
        else:
            base_capabilities = {"class_mapping_validation": "unavailable", "detector_available": False}
            base_available = False
            base_classes = [
                person_names.get(class_id, f"class_{class_id}")
                for class_id in sorted(set(person_config.target_classes))
            ]
            base_weapon_classes = [
                person_names.get(class_id, f"class_{class_id}")
                for class_id in sorted(set(person_config.target_classes) & set(person_config.weapon_classes))
            ]
        weapon_capabilities = self.weapon_detector.get_capabilities()
        custom_weapon_classes = list(weapon_capabilities["supported_classes"])
        custom_available = bool(weapon_capabilities["weapon_detection_supported"])
        available_custom_classes = custom_weapon_classes if custom_available else []
        supported_weapon_classes = self._unique_labels([*base_weapon_classes, *available_custom_classes])
        supported_classes = self._unique_labels([*base_classes, *available_custom_classes])
        supported_families = {self._label_family(value) for value in supported_weapon_classes}
        unsupported_concepts = []
        if "weapon" not in supported_families:
            unsupported_concepts.append("generic weapon")
        if "sharp object" not in supported_families:
            unsupported_concepts.append("generic sharp object")
        if "firearm" not in supported_families:
            unsupported_concepts.extend(["gun", "pistol"])

        return {
            "model_name": person_config.model_path,
            "base_detector_available": base_available,
            "supported_classes": supported_classes,
            "supported_weapon_classes": supported_weapon_classes,
            "unsupported_weapon_concepts": unsupported_concepts,
            "weapon_detection_supported": bool(supported_weapon_classes),
            "person_detector": {
                "model_name": person_config.model_path,
                "detector_available": base_available,
                "availability": base_capabilities.get("availability", "unavailable"),
                "unavailable_reason": base_capabilities.get("unavailable_reason"),
                "supported_classes": base_classes,
                "weapon_classes": base_weapon_classes,
                "weapon_detection_supported": bool(base_weapon_classes),
                "class_mapping_validation": base_capabilities.get("class_mapping_validation"),
            },
            "weapon_detector": {
                "model_name": weapon_capabilities["model_name"],
                "supported_classes": custom_weapon_classes,
                "available_classes": available_custom_classes,
                "internal_class_ids": weapon_capabilities["internal_class_ids"],
                "weapon_detection_supported": custom_available,
                "class_mapping_validated": weapon_capabilities.get("class_mapping_validated", False),
                "validation_status": weapon_capabilities.get("validation_status"),
                "disabled_reason": weapon_capabilities.get("disabled_reason"),
                "limitation": (
                    None
                    if custom_available
                    else weapon_capabilities.get("disabled_reason")
                    or "Custom weapon detector weights are unavailable."
                ),
            },
            "action_recognition_supported": False,
            "pose_estimation_supported": False,
            "semantic_verification_supported": False,
        }

    @classmethod
    def _merge_detections(
        cls,
        base_detections: List[Detection],
        custom_weapon_detections: List[Detection],
    ) -> List[Detection]:
        """Suppress duplicate weapon boxes emitted by both local models."""
        merged = list(base_detections)
        for custom in custom_weapon_detections:
            duplicate_index = None
            for index, existing in enumerate(merged):
                if not existing.is_weapon:
                    continue
                if cls._label_family(existing.class_name) != cls._label_family(custom.class_name):
                    continue
                if cls._bbox_iou(existing.bbox, custom.bbox) >= 0.50:
                    duplicate_index = index
                    break
            if duplicate_index is None:
                merged.append(custom)
            elif custom.confidence >= merged[duplicate_index].confidence:
                merged[duplicate_index] = custom
        return merged

    @staticmethod
    def _bbox_iou(first, second) -> float:
        x1 = max(first[0], second[0])
        y1 = max(first[1], second[1])
        x2 = min(first[2], second[2])
        y2 = min(first[3], second[3])
        intersection = max(0, x2 - x1) * max(0, y2 - y1)
        if intersection <= 0:
            return 0.0
        first_area = max(0, first[2] - first[0]) * max(0, first[3] - first[1])
        second_area = max(0, second[2] - second[0]) * max(0, second[3] - second[1])
        union = first_area + second_area - intersection
        return intersection / union if union > 0 else 0.0

    @staticmethod
    def _label_family(value: str) -> str:
        normalized = " ".join(str(value).strip().lower().replace("_", " ").split())
        if normalized in {"gun", "pistol", "firearm", "handgun"}:
            return "firearm"
        return normalized

    @classmethod
    def _unique_labels(cls, values: List[str]) -> List[str]:
        unique: List[str] = []
        seen: set[str] = set()
        for value in values:
            identity = cls._label_family(value)
            if identity not in seen:
                unique.append(value)
                seen.add(identity)
        return unique

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
