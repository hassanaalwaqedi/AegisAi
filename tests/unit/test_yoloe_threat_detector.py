from pathlib import Path

import numpy as np

from config import DetectionConfig
from aegis.detection.multi_model_detector import MultiModelDetector
from aegis.detection.yolo_detector import Detection
from aegis.detection.yoloe_threat_detector import YOLOEThreatDetector


PROMPTS = ("handgun", "pistol", "knife")


class _Value:
    def __init__(self, value):
        self.value = value

    def cpu(self):
        return self

    def numpy(self):
        return np.array(self.value)


class _Boxes:
    def __init__(self):
        self.cls = [_Value(0)]
        self.xyxy = [_Value([1, 2, 30, 40])]
        self.conf = [_Value(0.91)]

    def __len__(self):
        return 1


class _Result:
    boxes = _Boxes()
    masks = object()


class _YOLOE:
    instances = []

    def __init__(self, path):
        self.ckpt_path = path
        self.task = "segment"
        self.device = "cpu"
        self.names = {}
        self.loaded_embedding_path = None
        self.set_classes_calls = 0
        self.__class__.instances.append(self)

    def load_prompt_embeddings(self, path):
        self.loaded_embedding_path = path
        # This mirrors Ultralytics: saved embeddings are bound once at load
        # time through set_classes(), without calling the text encoder.
        self.set_classes(PROMPTS, object())

    def set_classes(self, names, *_args, **_kwargs):
        self.set_classes_calls += 1
        self.names = dict(enumerate(names))

    def get_text_pe(self, *_args, **_kwargs):
        raise AssertionError("runtime must not initialize text prompts")

    def predict(self, **_kwargs):
        return [_Result()]


def _config(tmp_path: Path, **overrides):
    checkpoint = tmp_path / "yoloe-26n-seg.pt"
    embeddings = tmp_path / "yoloe-26n-seg.threat-prompts.npz"
    checkpoint.write_bytes(b"checkpoint")
    embeddings.write_bytes(b"embeddings")
    defaults = {
        "threat_detector_enabled": True,
        "threat_model_path": str(checkpoint),
        "threat_prompt_embeddings_path": str(embeddings),
        "threat_classes": PROMPTS,
        "threat_frame_skip": 3,
    }
    defaults.update(overrides)
    return DetectionConfig(**defaults)


def test_yoloe_binds_persisted_embeddings_once_without_text_encoder_initialization(monkeypatch, tmp_path):
    monkeypatch.setattr("aegis.detection.yoloe_threat_detector.YOLOE", _YOLOE)
    detector = YOLOEThreatDetector(detection_config=_config(tmp_path))

    detector.preload()

    instance = _YOLOE.instances[-1]
    assert instance.loaded_embedding_path.endswith(".npz")
    assert instance.set_classes_calls == 1
    detector.detect(np.zeros((48, 48, 3), dtype=np.uint8))
    detector.detect(np.zeros((48, 48, 3), dtype=np.uint8))
    assert instance.set_classes_calls == 1
    runtime = detector.get_runtime_metadata()
    assert runtime["ready"] is True
    assert runtime["prompt_mode"] == "precomputed_text_embeddings"
    assert runtime["classes"] == list(PROMPTS)


def test_yoloe_normalizes_candidate_with_provenance_and_keeps_risk_flag_false(monkeypatch, tmp_path):
    monkeypatch.setattr("aegis.detection.yoloe_threat_detector.YOLOE", _YOLOE)
    detector = YOLOEThreatDetector(detection_config=_config(tmp_path))

    detections = detector.detect(np.zeros((48, 48, 3), dtype=np.uint8))

    assert len(detections) == 1
    detection = detections[0]
    assert detection.class_name == "handgun"
    assert detection.bbox == (1, 2, 30, 40)
    assert detection.detector == "threat_yoloe"
    assert detection.evidence_type == "threat_candidate"
    assert detection.model_source.endswith("yoloe-26n-seg.pt")
    assert detection.is_weapon is False
    assert detector.get_last_masks()


def test_yoloe_missing_embedding_is_truthful_degraded_state(monkeypatch, tmp_path):
    monkeypatch.setattr("aegis.detection.yoloe_threat_detector.YOLOE", _YOLOE)
    config = _config(tmp_path)
    Path(config.threat_prompt_embeddings_path).unlink()
    detector = YOLOEThreatDetector(detection_config=config)

    try:
        detector.preload()
    except FileNotFoundError:
        pass

    runtime = detector.get_runtime_metadata()
    assert runtime["ready"] is False
    assert "prompt embeddings" in runtime["error"]


class _GeneralDetector:
    def __init__(self):
        self.calls = 0

    def detect(self, _frame):
        self.calls += 1
        return [Detection((0, 0, 1, 1), 0.9, 0, "person", is_person=True)]


class _WeaponDetector:
    def detect(self, _frame):
        return []


class _ThreatDetector:
    enabled = True

    def __init__(self):
        self.calls = 0

    def detect(self, _frame):
        self.calls += 1
        return [
            Detection(
                (2, 2, 4, 4), 0.8, 2000, "handgun",
                object_category="threat_candidate", detector="threat_yoloe", evidence_type="threat_candidate",
            )
        ]


def test_multimodel_runs_general_every_frame_and_threat_at_configured_cadence(tmp_path):
    general = _GeneralDetector()
    threat = _ThreatDetector()
    detector = MultiModelDetector(
        detection_config=_config(tmp_path),
        person_detector=general,
        weapon_detector=_WeaponDetector(),
        threat_detector=threat,
    )

    outputs = [detector.detect(np.zeros((8, 8, 3), dtype=np.uint8)) for _ in range(4)]

    assert general.calls == 4
    assert threat.calls == 2  # frames one and four at frame_skip=3
    assert [item.detector for item in outputs[0]] == ["general_yolo", "threat_yoloe"]
    assert [item.detector for item in outputs[1]] == ["general_yolo"]
