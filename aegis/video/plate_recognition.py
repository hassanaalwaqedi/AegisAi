"""Plate recognition interfaces with lazy optional PaddleOCR support."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Protocol, Sequence

import numpy as np

from aegis.video.plate_validation import validate_turkish_plate
from aegis.video.vehicle_types import OCRCandidate, PlateRecognitionResult


class PlateDetector(Protocol):
    def detect_plate(self, vehicle_crop: np.ndarray) -> Optional[np.ndarray]: ...


class OCRProvider(Protocol):
    def read(self, plate_crop: np.ndarray) -> Sequence[OCRCandidate]: ...


class LocalUltralyticsPlateDetector:
    """Optional local plate detector; model weights must already exist."""

    def __init__(self, model_path: str) -> None:
        self.model_path = Path(model_path) if model_path else None
        self.unavailable_reason: Optional[str] = None
        self._model = None
        if not self.model_path:
            self.unavailable_reason = "plate_detector_not_configured"
        elif not self.model_path.exists():
            self.unavailable_reason = "plate_detector_model_missing"

    def detect_plate(self, vehicle_crop: np.ndarray) -> Optional[np.ndarray]:
        if self.unavailable_reason:
            return None
        try:
            if self._model is None:
                from ultralytics import YOLO
                self._model = YOLO(str(self.model_path))
            results = self._model(vehicle_crop, verbose=False)
            boxes = getattr(results[0], "boxes", None) if results else None
            if boxes is None or len(boxes) == 0:
                return None
            x1, y1, x2, y2 = (int(round(float(value))) for value in boxes.xyxy[0].tolist())
            height, width = vehicle_crop.shape[:2]
            x1, x2 = sorted((max(0, min(width, x1)), max(0, min(width, x2))))
            y1, y2 = sorted((max(0, min(height, y1)), max(0, min(height, y2))))
            return vehicle_crop[y1:y2, x1:x2] if x2 > x1 and y2 > y1 else None
        except Exception:
            self.unavailable_reason = "plate_detector_error"
            return None


def resolve_ocr_device(requested: str = "auto", cuda_available: Optional[bool] = None) -> str:
    if requested == "cpu":
        return "cpu"
    if cuda_available is None:
        try:
            import torch
            cuda_available = bool(torch.cuda.is_available())
        except Exception:
            cuda_available = False
    return "gpu" if requested == "gpu" and cuda_available else ("gpu" if requested == "auto" and cuda_available else "cpu")


class PaddleOCRProvider:
    """Lazy OCR adapter.  It never downloads models: model_dir must exist."""

    def __init__(self, model_dir: str, device: str = "auto") -> None:
        self.model_dir = Path(model_dir) if model_dir else None
        self.device = resolve_ocr_device(device)
        self.unavailable_reason: Optional[str] = None
        self._engine = None
        if not self.model_dir:
            self.unavailable_reason = "ocr_model_not_configured"
        elif not self.model_dir.exists():
            self.unavailable_reason = "ocr_model_path_missing"

    def read(self, plate_crop: np.ndarray) -> Sequence[OCRCandidate]:
        if self.unavailable_reason:
            return []
        try:
            if self._engine is None:
                from paddleocr import PaddleOCR  # isolated optional runtime
                self._engine = PaddleOCR(
                    lang="en",
                    device=self.device,
                    text_recognition_model_dir=str(self.model_dir),
                )
            output = self._engine.predict(plate_crop)
        except ImportError:
            self.unavailable_reason = "paddleocr_unavailable"
            return []
        except Exception:
            self.unavailable_reason = "ocr_provider_error"
            return []
        candidates: list[OCRCandidate] = []
        for item in output or []:
            texts = item.get("rec_texts", []) if isinstance(item, dict) else []
            scores = item.get("rec_scores", []) if isinstance(item, dict) else []
            candidates.extend(OCRCandidate(str(text), float(scores[index]) if index < len(scores) else None) for index, text in enumerate(texts))
        return candidates


class PlateRecognitionService:
    def __init__(self, *, enabled: bool, detector: Optional[PlateDetector] = None, ocr: Optional[OCRProvider] = None) -> None:
        self.enabled = enabled
        self.detector = detector
        self.ocr = ocr

    def recognize(self, vehicle_crop: np.ndarray) -> PlateRecognitionResult:
        if not self.enabled:
            return PlateRecognitionResult(False, reason="disabled")
        if self.detector is None:
            return PlateRecognitionResult(False, reason="plate_detector_not_configured")
        if self.ocr is None:
            return PlateRecognitionResult(False, reason="ocr_provider_not_configured")
        plate_crop = self.detector.detect_plate(vehicle_crop)
        if plate_crop is None or plate_crop.size == 0:
            return PlateRecognitionResult(True, reason=getattr(self.detector, "unavailable_reason", None) or "plate_not_detected")
        candidates = list(self.ocr.read(plate_crop))
        if not candidates:
            return PlateRecognitionResult(True, reason=getattr(self.ocr, "unavailable_reason", None) or "no_ocr_text")
        for candidate in sorted(candidates, key=lambda value: value.confidence or 0.0, reverse=True):
            validated = validate_turkish_plate(candidate.text)
            if validated.valid:
                return PlateRecognitionResult(True, True, validated.normalized, candidate.confidence)
        return PlateRecognitionResult(True, False, reason="invalid_ocr_result")
