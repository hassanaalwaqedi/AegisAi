from types import SimpleNamespace

import numpy as np

from config import DetectionConfig
from aegis.detection.multi_model_detector import MultiModelDetector
from aegis.detection.weapon_detector import WeaponDetector
from aegis.detection.yolo_detector import Detection


class _FakeTensor:
    def __init__(self, value):
        self._value = value

    def cpu(self):
        return self

    def numpy(self):
        return self._value


class _FakeBoxes:
    def __init__(self):
        self.xyxy = [_FakeTensor(np.array([10, 20, 40, 70]))]
        self.conf = [_FakeTensor(np.array(0.91))]
        self.cls = [_FakeTensor(np.array(0))]

    def __len__(self):
        return 1


class _FakeWeaponModel:
    def predict(self, **_kwargs):
        return [SimpleNamespace(boxes=_FakeBoxes())]


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
