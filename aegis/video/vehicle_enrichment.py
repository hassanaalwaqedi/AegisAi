"""Tracker-aware, opt-in vehicle enrichment orchestration.

This module is deliberately sidecar-like: its failures, disabled state, and
missing optional models never affect the detector, ByteTrack, risk score, or
camera streaming loop.
"""

from __future__ import annotations

import time
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np

from aegis.settings import VehicleEnrichmentSettings
from aegis.video.evidence_deduplication import EvidenceDeduplicator
from aegis.video.frame_quality import FrameQualityGate
from aegis.video.metrics import NoopVehicleMetrics, VehicleMetrics
from aegis.video.plate_recognition import (
    LocalUltralyticsPlateDetector,
    PaddleOCRProvider,
    PlateRecognitionService,
)
from aegis.video.vehicle_color import VehicleColorService
from aegis.video.vehicle_make_model import LocalVehicleMakeModelService
from aegis.video.vehicle_types import (
    ColorEstimate,
    DeduplicationDecision,
    FrameQuality,
    MakeModelEstimate,
    PlateRecognitionResult,
    VehicleEnrichmentResult,
)


@dataclass
class _TrackCandidate:
    last_run: float = 0.0
    crop: Optional[np.ndarray] = None
    quality: Optional[FrameQuality] = None
    last_seen: float = 0.0


class VehicleEnrichmentScheduler:
    """Keeps only the sharpest recent crop for each internal tracked vehicle."""

    def __init__(self, *, interval_seconds: float = 1.5, ttl_seconds: float = 120.0, cache_limit: int = 500) -> None:
        self.interval_seconds = interval_seconds
        self.ttl_seconds = ttl_seconds
        self.cache_limit = cache_limit
        self._state: OrderedDict[tuple[str, str], _TrackCandidate] = OrderedDict()

    def select(self, camera_id: str, track_id: str, crop: np.ndarray, quality: FrameQuality, now: Optional[float] = None) -> tuple[bool, np.ndarray, FrameQuality, str]:
        current = time.monotonic() if now is None else now
        self._prune(current)
        key = (camera_id, track_id)
        state = self._state.get(key, _TrackCandidate())
        if quality.accepted and (state.quality is None or quality.sharpness >= state.quality.sharpness):
            state.crop = crop.copy()
            state.quality = quality
        state.last_seen = current
        self._state[key] = state
        self._state.move_to_end(key)
        while len(self._state) > self.cache_limit:
            self._state.popitem(last=False)
        if not quality.accepted:
            return False, crop, quality, quality.reason or "quality_rejected"
        if state.last_run and current - state.last_run < self.interval_seconds:
            return False, crop, quality, "throttled"
        selected_crop = state.crop if state.crop is not None else crop
        selected_quality = state.quality if state.quality is not None else quality
        state.last_run = current
        state.crop = None
        state.quality = None
        return True, selected_crop, selected_quality, "scheduled"

    def _prune(self, current: float) -> None:
        for key in [key for key, item in self._state.items() if current - item.last_seen > self.ttl_seconds]:
            self._state.pop(key, None)


class RestrictedVehicleEvidenceStore:
    """Small process-local restricted store for validated plate evidence.

    It deliberately has no route.  A production RBAC/audit/retention service is
    needed before this data can be exposed.  Values are bounded in memory and
    are never written into the default operator payloads or Prometheus labels.
    """

    def __init__(self, max_items: int = 500) -> None:
        self._items: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self.max_items = max_items

    def save(self, *, camera_id: str, track_id: str, plate_text: str, quality: FrameQuality) -> None:
        key = f"{camera_id}:{track_id}:{time.monotonic_ns()}"
        self._items[key] = {
            "camera_id": camera_id,
            "track_id": track_id,
            "plate_text": plate_text,
            "quality": quality.to_dict(),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        while len(self._items) > self.max_items:
            self._items.popitem(last=False)


class VehicleEnrichmentService:
    def __init__(
        self,
        settings: VehicleEnrichmentSettings,
        *,
        quality_gate: Optional[FrameQualityGate] = None,
        scheduler: Optional[VehicleEnrichmentScheduler] = None,
        plate_service: Optional[PlateRecognitionService] = None,
        color_service: Optional[VehicleColorService] = None,
        make_model_service: Optional[LocalVehicleMakeModelService] = None,
        deduplicator: Optional[EvidenceDeduplicator] = None,
        evidence_store: Optional[RestrictedVehicleEvidenceStore] = None,
        metrics: Optional[VehicleMetrics | NoopVehicleMetrics] = None,
    ) -> None:
        self.settings = settings
        self.quality_gate = quality_gate or FrameQualityGate(
            min_width=settings.min_crop_width,
            min_height=settings.min_crop_height,
            min_sharpness=settings.min_sharpness,
            min_brightness=settings.min_brightness,
        )
        self.scheduler = scheduler or VehicleEnrichmentScheduler(
            interval_seconds=settings.interval_seconds,
            ttl_seconds=settings.tracker_state_ttl_seconds,
            cache_limit=settings.tracker_cache_limit,
        )
        self.plate_service = plate_service or PlateRecognitionService(
            enabled=settings.plate_ocr_enabled,
            detector=LocalUltralyticsPlateDetector(settings.plate_detector_model_path)
            if settings.plate_ocr_enabled else None,
            ocr=PaddleOCRProvider(settings.plate_ocr_model_dir, settings.plate_ocr_device)
            if settings.plate_ocr_enabled else None,
        )
        self.color_service = color_service or VehicleColorService(settings.vehicle_color_enabled)
        self.make_model_service = make_model_service or LocalVehicleMakeModelService(
            enabled=settings.vehicle_make_model_enabled,
            model_path=settings.vehicle_make_model_model_path,
            labels_path=settings.vehicle_make_model_labels_path,
            architecture=settings.vehicle_make_model_architecture,
        )
        self.deduplicator = deduplicator or EvidenceDeduplicator(
            enabled=settings.evidence_deduplication_enabled,
            max_distance=settings.evidence_phash_max_distance,
            retention_seconds=settings.evidence_retention_seconds,
            cache_limit=settings.evidence_cache_limit,
        )
        self.evidence_store = evidence_store or RestrictedVehicleEvidenceStore(settings.evidence_cache_limit)
        self.metrics = metrics or VehicleMetrics()
        self._frame_budget: OrderedDict[str, int] = OrderedDict()
        self._frame_budget_lock = threading.Lock()

    def enrich(
        self,
        *,
        camera_id: str,
        track_id: str,
        frame: np.ndarray,
        bbox: tuple[float, float, float, float] | list[float],
        high_priority: bool = False,
        manual: bool = False,
        frame_token: Optional[str] = None,
    ) -> VehicleEnrichmentResult:
        if not self.settings.enabled:
            return self._disabled_result()
        started = time.perf_counter()
        self.metrics.request()
        try:
            crop = self._crop(frame, bbox)
            quality = self.quality_gate.evaluate(crop)
            should_run, selected_crop, selected_quality, schedule_reason = self.scheduler.select(camera_id, track_id, crop, quality)
            if not quality.accepted:
                return VehicleEnrichmentResult("skipped", quality, quality.reason)
            if not should_run:
                return VehicleEnrichmentResult("throttled", quality, schedule_reason)
            if frame_token and not self._consume_frame_budget(frame_token):
                return VehicleEnrichmentResult("throttled", selected_quality, "frame_capacity_reached")
            duplicate = self.deduplicator.should_store(camera_id, track_id, selected_crop, manual=manual, high_priority=high_priority)
            if duplicate.skip:
                self.metrics.duplicate()
                return VehicleEnrichmentResult("deduplicated", selected_quality, duplicate.reason, deduplication=duplicate)
            color = self.color_service.estimate(selected_crop, selected_quality)
            plate = PlateRecognitionResult(False, reason="disabled")
            if self.settings.plate_ocr_enabled:
                self.metrics.plate_attempt()
                plate = self.plate_service.recognize(selected_crop)
                if plate.valid:
                    self.metrics.plate_valid()
                else:
                    self.metrics.plate_failure()
            make_model = self.make_model_service.classify(selected_crop)
            saved = False
            if plate.valid and plate.plate_text:
                self.evidence_store.save(camera_id=camera_id, track_id=track_id, plate_text=plate.plate_text, quality=selected_quality)
                saved = True
            self.metrics.success()
            return VehicleEnrichmentResult("completed", selected_quality, color=color, plate=plate, make_model=make_model, deduplication=duplicate, evidence_saved=saved)
        except Exception:
            # Enrichment must never interrupt the detector/tracker control path.
            return VehicleEnrichmentResult("unavailable", FrameQuality(False, reason="enrichment_error"), "enrichment_error")
        finally:
            self.metrics.duration(time.perf_counter() - started)

    def _disabled_result(self) -> VehicleEnrichmentResult:
        return VehicleEnrichmentResult("disabled", FrameQuality(False, reason="disabled"), "disabled")

    def _consume_frame_budget(self, frame_token: str) -> bool:
        """Allow only the configured number of costly enrichments per frame."""
        with self._frame_budget_lock:
            count = self._frame_budget.get(frame_token, 0)
            if count >= self.settings.max_enrichments_per_frame:
                return False
            self._frame_budget[frame_token] = count + 1
            self._frame_budget.move_to_end(frame_token)
            while len(self._frame_budget) > 32:
                self._frame_budget.popitem(last=False)
            return True

    @staticmethod
    def _crop(frame: np.ndarray, bbox: tuple[float, float, float, float] | list[float]) -> np.ndarray:
        if not isinstance(frame, np.ndarray) or frame.ndim < 2 or len(bbox) != 4:
            return np.empty((0, 0), dtype=np.uint8)
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = (int(round(float(value))) for value in bbox)
        x1, x2 = sorted((max(0, min(width, x1)), max(0, min(width, x2))))
        y1, y2 = sorted((max(0, min(height, y1)), max(0, min(height, y2))))
        return frame[y1:y2, x1:x2]
