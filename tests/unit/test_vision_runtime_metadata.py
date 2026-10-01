"""Regression coverage for vision configuration/runtime drift."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from aegis.detection.yolo_detector import YOLODetector
from aegis.settings import get_settings
from config import DetectionConfig


def test_environment_model_path_reaches_legacy_camera_adapter(monkeypatch, tmp_path):
    configured = tmp_path / "configured.pt"
    monkeypatch.setenv("AEGIS_DETECTION_MODEL_PATH", str(configured))
    get_settings.cache_clear()
    try:
        assert DetectionConfig().model_path == str(configured)
    finally:
        get_settings.cache_clear()


def test_missing_checkpoint_is_degraded_without_a_fallback(tmp_path):
    missing = tmp_path / "missing.pt"
    detector = YOLODetector(detection_config=DetectionConfig(model_path=str(missing)))

    metadata = detector.get_runtime_metadata()

    assert metadata["ready"] is False
    assert metadata["configured_path"] == str(missing)
    assert metadata["model"] == "missing.pt"
    assert "unavailable" in metadata["error"].lower()


def test_runtime_metadata_is_derived_from_the_loaded_model(monkeypatch, tmp_path):
    checkpoint = tmp_path / "actual.pt"
    checkpoint.write_bytes(b"test")

    class FakeTorchModel:
        yaml = {"yaml_file": "actual.yaml"}

        def parameters(self):
            yield SimpleNamespace(dtype="float32")

    class FakeYOLO:
        def __init__(self, path):
            self.ckpt_path = path
            self.task = "detect"
            self.names = {0: "actual-person", 1: "actual-car"}
            self.device = "cpu"
            self.model = FakeTorchModel()
            self.predictor = SimpleNamespace(
                model=SimpleNamespace(device="cuda:0", fp16=True),
            )

    monkeypatch.setattr("aegis.detection.yolo_detector.YOLO", FakeYOLO)
    detector = YOLODetector(detection_config=DetectionConfig(model_path=str(checkpoint)), device="cuda:0")
    metadata = detector.model and detector.get_runtime_metadata()

    assert metadata["ready"] is True
    assert metadata["resolved_path"] == str(checkpoint.resolve())
    assert metadata["model"] == "actual.pt"
    assert metadata["task"] == "detect"
    assert metadata["class_count"] == 2
    assert metadata["classes"] == ["actual-person", "actual-car"]
    assert metadata["device"] == "cuda:0"
    assert metadata["requested_device"] == "cuda:0"
    assert metadata["precision"] == "FP16"


def test_active_inference_metrics_come_from_the_ultralytics_prediction(monkeypatch, tmp_path):
    checkpoint = tmp_path / "benchmark.pt"
    checkpoint.write_bytes(b"test")
    calls = []

    class FakeTorchModel:
        yaml = {"yaml_file": "benchmark.yaml"}

        def parameters(self):
            yield SimpleNamespace(dtype="float32")

    class FakeYOLO:
        def __init__(self, path):
            self.ckpt_path = path
            self.task = "detect"
            self.names = {0: "person"}
            self.device = "cpu"
            self.model = FakeTorchModel()
            self.predictor = None

        def predict(self, **kwargs):
            calls.append(kwargs)
            self.predictor = SimpleNamespace(
                model=SimpleNamespace(device="cuda:0", fp16=False),
            )
            return [SimpleNamespace(
                boxes=None,
                speed={"preprocess": 1.0, "inference": 3.0, "postprocess": 2.0},
            )]

    monkeypatch.setattr("aegis.detection.yolo_detector.YOLO", FakeYOLO)
    detector = YOLODetector(
        detection_config=DetectionConfig(model_path=str(checkpoint)),
        device="cuda:0",
    )
    assert detector.detect(np.zeros((32, 32, 3), dtype=np.uint8)) == []

    metadata = detector.get_runtime_metadata()
    assert calls[0]["device"] == "cuda:0"
    assert metadata["device"] == "cuda:0"
    assert metadata["precision"] == "FP32"
    assert metadata["performance"]["measured_frames"] == 1
    assert metadata["performance"]["avg_preprocessing_ms"] == 1.0
    assert metadata["performance"]["avg_inference_ms"] == 3.0
    assert metadata["performance"]["avg_postprocessing_ms"] >= 2.0
    assert metadata["performance"]["avg_end_to_end_ms"] is not None
    assert metadata["performance"]["effective_fps"] is not None


def test_multimodel_detector_passes_the_selected_device_to_yolo_wrappers():
    from aegis.detection.multi_model_detector import MultiModelDetector

    detector = MultiModelDetector(detection_config=DetectionConfig(), device="cuda:0")

    assert detector.person_detector._device == "cuda:0"
    assert detector.weapon_detector._device == "cuda:0"
