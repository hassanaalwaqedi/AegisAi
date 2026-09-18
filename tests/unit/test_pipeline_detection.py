"""Detector startup readiness tests."""

from __future__ import annotations

import pytest

from aegis.pipeline.detection import DetectionStage


def test_preload_model_uses_the_stage_configuration_and_loads_real_weights_boundary(monkeypatch):
    import aegis.detection.multi_model_detector as detector_module

    captured = {}

    class FakeDetector:
        def __init__(self, *, detection_config):
            captured["config"] = detection_config
            self.person_detector = self
            self.weapon_detector = self

        @property
        def model(self):
            captured["weights_loaded"] = True
            return object()

        def get_capabilities(self):
            return {"weapon_detection_supported": False}

        def get_model_capabilities(self):
            return {"weapon_detection_supported": True}

    monkeypatch.setattr(detector_module, "MultiModelDetector", FakeDetector)
    stage = DetectionStage(model_path="verified-yolo.pt", confidence=0.61)

    stage.preload_model()

    assert captured["config"].model_path == "verified-yolo.pt"
    assert captured["config"].confidence_threshold == 0.61
    assert captured["weights_loaded"]
    assert stage.get_model_info()["loaded"] is True
    assert stage._model_load_error is None


def test_preload_model_retains_a_truthful_failure_reason(monkeypatch):
    import aegis.detection.multi_model_detector as detector_module

    class FailingDetector:
        def __init__(self, *, detection_config):
            del detection_config
            self.person_detector = self
            self.weapon_detector = self

        @property
        def model(self):
            raise FileNotFoundError("verified-yolo.pt")

        def get_capabilities(self):
            return {"weapon_detection_supported": False}

    monkeypatch.setattr(detector_module, "MultiModelDetector", FailingDetector)
    stage = DetectionStage(model_path="verified-yolo.pt")

    with pytest.raises(FileNotFoundError):
        stage.preload_model()

    assert "FileNotFoundError" in (stage._model_load_error or "")
