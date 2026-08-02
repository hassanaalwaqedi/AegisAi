"""Fast, model-free tests for the optional vehicle enrichment sidecar."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from aegis.settings import VehicleEnrichmentSettings
from aegis.video.evidence_deduplication import EvidenceDeduplicator
from aegis.video.frame_quality import FrameQualityGate
from aegis.video.metrics import VehicleMetrics, metrics_payload
from aegis.video.plate_recognition import PlateRecognitionService, resolve_ocr_device
from aegis.video.plate_validation import validate_turkish_plate
from aegis.video.vehicle_color import VehicleColorService
from aegis.video.vehicle_enrichment import VehicleEnrichmentScheduler, VehicleEnrichmentService
from aegis.video.vehicle_make_model import LocalVehicleMakeModelService
from aegis.video.vehicle_types import FrameQuality, OCRCandidate, PlateRecognitionResult, VehicleEnrichmentResult


def _sharp_image(width: int = 320, height: int = 180) -> np.ndarray:
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:, ::2] = (30, 130, 220)
    image[::2, :] = (200, 40, 15)
    return image


def test_frame_quality_rejects_small_dark_and_blurred_crops() -> None:
    gate = FrameQualityGate(min_width=160, min_height=80, min_sharpness=80, min_brightness=35)
    assert gate.evaluate(np.zeros((20, 20, 3), dtype=np.uint8)).reason == "too_small"
    assert gate.evaluate(np.zeros((100, 200, 3), dtype=np.uint8)).reason == "low_light"
    assert gate.evaluate(np.full((100, 200, 3), 120, dtype=np.uint8)).reason == "too_blurry"
    assert gate.evaluate(_sharp_image()).accepted is True


def test_turkish_plate_validation_is_conservative_with_limited_position_fixes() -> None:
    assert validate_turkish_plate("34 ABC 123").normalized == "34 ABC 123"
    assert validate_turkish_plate("06-ab-1234").normalized == "06 AB 1234"
    assert validate_turkish_plate("34 A8C I23").normalized == "34 ABC 123"
    assert validate_turkish_plate("82 ABC 123").valid is False
    assert validate_turkish_plate("not a plate").valid is False


class _PlateDetector:
    def detect_plate(self, vehicle_crop: np.ndarray) -> np.ndarray:
        return vehicle_crop


class _OCR:
    def __init__(self, *values: OCRCandidate) -> None:
        self.values = values

    def read(self, plate_crop: np.ndarray) -> list[OCRCandidate]:
        del plate_crop
        return list(self.values)


def test_ocr_accepts_only_valid_mocked_plate_candidates() -> None:
    crop = _sharp_image()
    valid = PlateRecognitionService(enabled=True, detector=_PlateDetector(), ocr=_OCR(OCRCandidate("34 ABC 123", 0.94))).recognize(crop)
    invalid = PlateRecognitionService(enabled=True, detector=_PlateDetector(), ocr=_OCR(OCRCandidate("noise", 0.99))).recognize(crop)
    disabled = PlateRecognitionService(enabled=False, detector=_PlateDetector(), ocr=_OCR()).recognize(crop)
    assert valid.valid and valid.plate_text == "34 ABC 123"
    assert not invalid.valid and invalid.plate_text is None
    assert disabled.reason == "disabled"


def test_color_prefers_unknown_for_inadequate_input() -> None:
    service = VehicleColorService(enabled=True)
    estimate = service.estimate(np.zeros((180, 320, 3), dtype=np.uint8), FrameQuality(True, 100, 100, 320, 180))
    assert estimate.label == "unknown"
    assert estimate.reason == "low_light"


def test_make_model_never_claims_a_result_without_local_weights() -> None:
    output = LocalVehicleMakeModelService(enabled=True).classify(_sharp_image())
    assert output.available is False
    assert output.reason == "model_not_configured"


def test_scheduler_throttles_and_keeps_state_bounded() -> None:
    scheduler = VehicleEnrichmentScheduler(interval_seconds=1.5, ttl_seconds=3, cache_limit=2)
    quality = FrameQuality(True, 100, 100, 320, 180)
    image = _sharp_image()
    assert scheduler.select("cam", "one", image, quality, now=1.0)[0] is True
    assert scheduler.select("cam", "one", image, quality, now=1.4)[3] == "throttled"
    assert scheduler.select("cam", "one", image, quality, now=2.6)[0] is True


def test_deduplication_preserves_manual_and_high_priority_evidence() -> None:
    dedupe = EvidenceDeduplicator(max_distance=8)
    image = _sharp_image()
    assert dedupe.should_store("cam", "track", image, now=1.0).skip is False
    assert dedupe.should_store("cam", "track", image, now=2.0).skip is True
    assert dedupe.should_store("cam", "track", image, manual=True, now=2.1).skip is False
    assert dedupe.should_store("cam", "track", image, high_priority=True, now=2.2).skip is False


def test_cpu_fallback_and_safe_default_configuration(monkeypatch) -> None:
    assert resolve_ocr_device("auto", cuda_available=False) == "cpu"
    settings = VehicleEnrichmentSettings(enabled=False)
    assert settings.enabled is False
    assert settings.plate_ocr_enabled is False
    assert settings.inference_backend == "torch"
    monkeypatch.setenv("VEHICLE_ENRICHMENT_ENABLED", "true")
    monkeypatch.setenv("VEHICLE_ENRICHMENT_INTERVAL_SECONDS", "2.0")
    configured = VehicleEnrichmentSettings()
    assert configured.enabled is True
    assert configured.interval_seconds == 2.0


def test_service_is_disabled_by_default_and_public_data_cannot_leak_plates() -> None:
    service = VehicleEnrichmentService(VehicleEnrichmentSettings(enabled=False))
    result = service.enrich(camera_id="cam", track_id="track", frame=_sharp_image(), bbox=(0, 0, 320, 180))
    payload = result.to_public_dict()
    assert result.status == "disabled"
    assert "plate_text" not in payload
    assert "34 ABC 123" not in repr(payload)


def test_service_enforces_max_enrichments_per_frame() -> None:
    settings = VehicleEnrichmentSettings(enabled=True, min_crop_width=16, min_crop_height=16, min_sharpness=0, min_brightness=0, max_enrichments_per_frame=1)
    service = VehicleEnrichmentService(settings)
    image = _sharp_image()
    first = service.enrich(camera_id="cam", track_id="one", frame=image, bbox=(0, 0, 320, 180), frame_token="cam:1")
    second = service.enrich(camera_id="cam", track_id="two", frame=image, bbox=(0, 0, 320, 180), frame_token="cam:1")
    assert first.status in {"completed", "deduplicated"}
    assert second.reason == "frame_capacity_reached"


def test_enabled_ocr_without_local_models_is_truthful_and_non_failing() -> None:
    settings = VehicleEnrichmentSettings(
        enabled=True,
        plate_ocr_enabled=True,
        min_crop_width=16,
        min_crop_height=16,
        min_sharpness=0,
        min_brightness=0,
    )
    result = VehicleEnrichmentService(settings).enrich(
        camera_id="cam", track_id="one", frame=_sharp_image(), bbox=(0, 0, 320, 180)
    )
    assert result.status == "completed"
    assert result.plate.valid is False
    assert result.plate.reason == "plate_detector_not_configured"


def test_metrics_are_created_without_sensitive_labels() -> None:
    metrics = VehicleMetrics()
    metrics.request()
    metrics.duration(0.001)
    payload, _ = metrics_payload()
    rendered = payload.decode("utf-8")
    assert "aegis_vehicle_enrichment_requests_total" in rendered
    assert "plate_text" not in rendered
    assert "camera_id" not in rendered


def test_camera_ingestion_keeps_vehicle_sidecar_out_of_detection_and_risk_logic(monkeypatch) -> None:
    """Vehicle enrichment is post-risk and only its sanitised view is emitted."""
    from aegis.analysis.analysis_types import BehaviorFlags, MotionState
    from aegis.video.camera_sources import FrameIngestionService

    service = FrameIngestionService()
    track = SimpleNamespace(
        track_id=7, bbox=(0, 0, 320, 180), class_id=2, class_name="Car",
        object_category="vehicle", is_person=False, is_weapon=False,
        is_vehicle=True, confidence=0.9, model_source="verified-yolo",
    )
    history = SimpleNamespace(
        current_position=SimpleNamespace(x=160, y=90), history_length=1, duration=0.1,
    )
    evidence = {
        "risk_level": "LOW", "risk_score": 0.0, "explanation": "Car detected",
        "reason_codes": [], "model_source": ["verified-yolo"], "evidence_type": "object_detection",
        "verification_status": "confirmed", "visual_evidence": {}, "weapon_class": None,
        "weapon_confidence": None, "person_track_id": None, "weapon_track_id": None,
        "association_type": None, "association_score": None, "stable_frames": 0,
        "evidence_objects": [],
    }
    sidecar_result = VehicleEnrichmentResult(
        "completed", FrameQuality(True, 100, 100, 320, 180),
        plate=PlateRecognitionResult(True, True, "34 ABC 123", 0.9),
    )
    monkeypatch.setattr(service, "_get_detector", lambda: SimpleNamespace(detect=lambda frame: [track]))
    monkeypatch.setattr(service, "_get_tracker", lambda camera_id: SimpleNamespace(update=lambda detections, frame: [track]))
    monkeypatch.setattr(service, "_get_history_manager", lambda camera_id: SimpleNamespace(update=lambda *args, **kwargs: None, get_history=lambda track_id: history))
    monkeypatch.setattr(service, "_get_motion_analyzer", lambda camera_id: SimpleNamespace(analyze_all=lambda history_manager: {7: MotionState()}))
    monkeypatch.setattr(service, "_get_behavior_analyzer", lambda camera_id: SimpleNamespace(analyze_all=lambda history_manager, motions: {7: BehaviorFlags()}))
    monkeypatch.setattr(service, "_get_crowd_analyzer", lambda camera_id: SimpleNamespace(analyze=lambda tracks, shape: SimpleNamespace(max_density=0, person_count=0)))
    monkeypatch.setattr(service, "_get_risk_engine", lambda *args: SimpleNamespace(compute_frame_risks=lambda **kwargs: SimpleNamespace(track_risks=[])))
    monkeypatch.setattr(service, "_get_proximity_engine", lambda camera_id: SimpleNamespace(assess=lambda *args, **kwargs: []))
    monkeypatch.setattr(service, "_get_association_engine", lambda camera_id: SimpleNamespace(assess=lambda *args, **kwargs: []))
    monkeypatch.setattr(service, "_apply_frame_rules", lambda **kwargs: (kwargs["base_score"], kwargs["base_level"], kwargs["base_explanation"], kwargs["factors"]))
    monkeypatch.setattr(service, "_build_evidence", lambda **kwargs: evidence)
    monkeypatch.setattr(service, "_maybe_generate_detection_event", lambda **kwargs: None)
    monkeypatch.setattr(service, "_maybe_generate_alert", lambda **kwargs: None)
    monkeypatch.setattr(service, "_get_vehicle_enrichment_service", lambda: SimpleNamespace(enrich=lambda **kwargs: sidecar_result))
    monkeypatch.setattr(service, "get_model_capabilities", lambda: {
        "model_name": "verified-yolo", "supported_classes": ["Car"], "weapon_detection_supported": False,
        "person_detector": {}, "weapon_detector": {}, "action_recognition_supported": False,
        "pose_estimation_supported": False, "semantic_verification_supported": False,
    })

    result = service.process_frame("camera", _sharp_image())
    payload = result["detections"][0]
    assert payload["risk_level"] == "LOW"
    assert payload["vehicle_enrichment"]["plate"]["validation_status"] == "valid"
    assert "plate_text" not in payload["vehicle_enrichment"]
    assert "34 ABC 123" not in repr(payload)
