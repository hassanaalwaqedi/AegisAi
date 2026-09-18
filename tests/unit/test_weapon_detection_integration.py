from types import SimpleNamespace

import numpy as np

from config import DetectionConfig
from aegis.detection.multi_model_detector import MultiModelDetector
from aegis.detection.weapon_detector import WeaponDetector
from aegis.detection.yolo_detector import Detection
from aegis.detection.yolo_detector import YOLODetector


class _FakeTensor:
    def __init__(self, value):
        self._value = value

    def cpu(self):
        return self

    def numpy(self):
        return self._value


class _FakeBoxes:
    def __init__(self, class_id=0, confidence=0.91):
        self.xyxy = [_FakeTensor(np.array([10, 20, 40, 70]))]
        self.conf = [_FakeTensor(np.array(confidence))]
        self.cls = [_FakeTensor(np.array(class_id))]

    def __len__(self):
        return 1


class _FakeWeaponModel:
    def predict(self, **_kwargs):
        return [SimpleNamespace(boxes=_FakeBoxes())]


class _FakeBaseModel:
    def __init__(self):
        self.kwargs = None

    def predict(self, **kwargs):
        self.kwargs = kwargs
        return [SimpleNamespace(boxes=_FakeBoxes(class_id=43, confidence=0.40))]


class _FakeDetector:
    def __init__(self, detections):
        self._detections = detections

    def detect(self, _frame):
        return list(self._detections)


def test_weapon_detector_maps_best_pt_classes_to_internal_weapon_ids():
    config = DetectionConfig(weapon_debug_enabled=False)
    detector = WeaponDetector(detection_config=config)
    detector._model = _FakeWeaponModel()

    detections = detector.detect(np.zeros((100, 100, 3), dtype=np.uint8))

    assert len(detections) == 1
    detection = detections[0]
    assert detection.class_id == 1000
    assert detection.source_class_id == 0
    assert detection.class_name == "knife"
    assert detection.object_category == "weapon"
    assert detection.is_weapon is True
    assert detection.confidence == 0.91
    assert detection.model_source == config.weapon_model_path


def test_base_yolo_preserves_real_low_threshold_knife_output_as_weapon():
    config = DetectionConfig(weapon_debug_enabled=False)
    detector = YOLODetector(detection_config=config)
    model = _FakeBaseModel()
    detector._model = model

    detections = detector.detect(np.zeros((100, 100, 3), dtype=np.uint8))

    assert model.kwargs["conf"] == config.weapon_confidence_threshold
    assert len(detections) == 1
    assert detections[0].class_name == "Knife"
    assert detections[0].is_weapon is True
    assert detections[0].object_category == "weapon"


def test_explicit_confidence_override_applies_to_weapon_classes():
    config = DetectionConfig(weapon_debug_enabled=False)
    detector = YOLODetector(detection_config=config)
    model = _FakeBaseModel()
    detector._model = model

    detections = detector.detect(
        np.zeros((100, 100, 3), dtype=np.uint8),
        confidence_threshold=0.90,
    )

    assert model.kwargs["conf"] == 0.90
    assert detections == []


def test_multi_model_detector_merges_person_and_weapon_detections_without_id_collision():
    person = Detection(
        bbox=(0, 0, 50, 100),
        confidence=0.8,
        class_id=0,
        class_name="Person",
        object_category="person",
        is_person=True,
        is_vehicle=False,
        model_source="yolo11n.pt",
        source_class_id=0,
    )
    weapon = Detection(
        bbox=(10, 20, 40, 70),
        confidence=0.91,
        class_id=1000,
        class_name="knife",
        object_category="weapon",
        is_weapon=True,
        model_source="best.pt",
        source_class_id=0,
    )
    detector = MultiModelDetector(
        detection_config=DetectionConfig(weapon_debug_enabled=False),
        person_detector=_FakeDetector([person]),
        weapon_detector=_FakeDetector([weapon]),
    )

    detections = detector.detect(np.zeros((100, 100, 3), dtype=np.uint8))

    assert [d.class_id for d in detections] == [0, 1000]
    assert any(d.is_person for d in detections)
    assert any(d.is_weapon for d in detections)


def test_multi_model_detector_deduplicates_overlapping_base_and_custom_knife():
    base_knife = Detection(
        bbox=(10, 20, 40, 70),
        confidence=0.72,
        class_id=43,
        class_name="Knife",
        object_category="weapon",
        is_weapon=True,
        model_source="yolo11n.pt",
        source_class_id=43,
    )
    custom_knife = Detection(
        bbox=(11, 21, 41, 71),
        confidence=0.91,
        class_id=1000,
        class_name="knife",
        object_category="weapon",
        is_weapon=True,
        model_source="best.pt",
        source_class_id=0,
    )
    detector = MultiModelDetector(
        detection_config=DetectionConfig(weapon_debug_enabled=False),
        person_detector=_FakeDetector([base_knife]),
        weapon_detector=_FakeDetector([custom_knife]),
    )

    detections = detector.detect(np.zeros((100, 100, 3), dtype=np.uint8))

    assert detections == [custom_knife]


def test_custom_weapon_capability_turns_off_after_runtime_failure(tmp_path):
    model_path = tmp_path / "weapon.pt"
    model_path.write_bytes(b"configured-local-weights")
    detector = WeaponDetector(
        detection_config=DetectionConfig(
            weapon_model_path=str(model_path),
            weapon_debug_enabled=False,
        )
    )
    detector._disabled_reason = "class mapping mismatch"

    capabilities = detector.get_capabilities()

    assert capabilities["weapon_detection_supported"] is False
    assert capabilities["disabled_reason"] == "class mapping mismatch"


def test_custom_weapon_class_mapping_is_configurable_from_environment(monkeypatch):
    monkeypatch.setenv("AEGIS_WEAPON_CLASS_NAMES_JSON", '{"0":"knife","1":"gun","2":"sharp object"}')
    monkeypatch.setenv("AEGIS_WEAPON_INTERNAL_CLASS_IDS_JSON", '{"0":1000,"1":1001,"2":1002}')

    config = DetectionConfig()

    assert config.weapon_model_class_names == {0: "knife", 1: "gun", 2: "sharp object"}
    assert config.weapon_internal_class_ids == {0: 1000, 1: 1001, 2: 1002}
