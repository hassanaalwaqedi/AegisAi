"""Regression coverage for vision configuration/runtime drift."""

from __future__ import annotations

from types import SimpleNamespace

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

    monkeypatch.setattr("aegis.detection.yolo_detector.YOLO", FakeYOLO)
    detector = YOLODetector(detection_config=DetectionConfig(model_path=str(checkpoint)))
    metadata = detector.model and detector.get_runtime_metadata()

    assert metadata["ready"] is True
    assert metadata["resolved_path"] == str(checkpoint.resolve())
    assert metadata["model"] == "actual.pt"
    assert metadata["task"] == "detect"
    assert metadata["class_count"] == 2
    assert metadata["classes"] == ["actual-person", "actual-car"]
