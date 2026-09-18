"""
AegisAI - Smart City Risk Intelligence System
YOLOv8 Object Detector Module

This module provides production-grade object detection using Ultralytics YOLOv8.
Designed for real-time detection of persons and vehicles in urban environments.

Features:
- Lazy model loading with automatic device selection
- Configurable confidence and NMS thresholds
- Class filtering for target objects only
- Standardized output format for downstream processing
"""

import logging
from typing import List, Tuple, Optional, NamedTuple
from pathlib import Path

import numpy as np
from ultralytics import YOLO

from config import DetectionConfig, AegisConfig

# Configure module logger
logger = logging.getLogger(__name__)


class Detection(NamedTuple):
    """
    Standardized detection result container.
    
    Attributes:
        bbox: Bounding box coordinates (x1, y1, x2, y2) in pixels
        confidence: Detection confidence score [0.0, 1.0]
        class_id: COCO class identifier
        class_name: Human-readable class name
        object_category: Category string (person/weapon/vehicle/animal/generic)
        is_weapon: Whether this detection is a weapon
        is_person: Whether this detection is a person
        is_vehicle: Whether this detection is a vehicle
        is_animal: Whether this detection is an animal
        model_source: Detector model that produced this detection
        source_class_id: Original class ID emitted by the detector model
    """
    bbox: Tuple[int, int, int, int]
    confidence: float
    class_id: int
    class_name: str
    object_category: str = "generic"
    is_weapon: bool = False
    is_person: bool = False
    is_vehicle: bool = False
    is_animal: bool = False
    model_source: str = ""
    source_class_id: Optional[int] = None


class YOLODetector:
    """
    Production-grade YOLOv8 object detector.
    
    Provides real-time object detection with configurable parameters
    and automatic hardware acceleration when available.
    
    Attributes:
        config: Detection configuration parameters
        model: Loaded YOLO model instance
        device: Compute device (cpu/cuda/mps)
        
    Example:
        >>> detector = YOLODetector(config)
        >>> detections = detector.detect(frame)
        >>> for det in detections:
        ...     print(f"{det.class_name}: {det.confidence:.2f}")
    """
    
    def __init__(
        self,
        config: Optional[AegisConfig] = None,
        detection_config: Optional[DetectionConfig] = None
    ):
        """
        Initialize the YOLOv8 detector.
        
        Args:
            config: Full AegisConfig instance (preferred)
            detection_config: DetectionConfig instance (alternative)
            
        Raises:
            ValueError: If neither config is provided
            FileNotFoundError: If model weights file doesn't exist locally
                and cannot be downloaded
        """
        if config is not None:
            self._config = config.detection
            self._device = config.get_device_string()
        elif detection_config is not None:
            self._config = detection_config
            self._device = ""
        else:
            # Use default configuration
            self._config = DetectionConfig()
            self._device = ""
        
        self._model: Optional[YOLO] = None
        self._class_names = dict(self._config.CLASS_NAMES)
        self._available_class_ids: Optional[set[int]] = None
        self._validated_weapon_classes: Optional[set[int]] = None
        self._model_load_error: Optional[str] = None
        
        logger.info(
            f"YOLODetector initialized with model={self._config.model_path}, "
            f"confidence={self._config.confidence_threshold}, "
            f"classes={self._config.target_classes}"
        )
    
    @property
    def model(self) -> YOLO:
        """
        Lazy-load the YOLO model on first access.
        
        This defers the heavy model loading until actually needed,
        improving startup time for applications that may not use
        detection immediately.
        
        Returns:
            Loaded YOLO model instance
        """
        if self._model is None:
            model_path = Path(self._config.model_path)
            if not model_path.is_file():
                self._model_load_error = f"Base detector weights are unavailable: {model_path}"
                raise FileNotFoundError(self._model_load_error)
            logger.info(f"Loading YOLO model: {self._config.model_path}")
            try:
                model = YOLO(str(model_path))
                self._validate_model_labels(model)
                self._model = model
                self._model_load_error = None
            except Exception as exc:
                self._model_load_error = f"{type(exc).__name__}: {exc}"
                raise
            
            # Log device information
            if hasattr(self._model, 'device'):
                logger.info(f"Model loaded on device: {self._model.device}")
        
        return self._model

    def _validate_model_labels(self, model: YOLO) -> None:
        """Use model-owned labels so configured IDs cannot be silently misnamed."""
        raw_names = getattr(model, "names", None)
        if isinstance(raw_names, (list, tuple)):
            actual_names = {index: str(name) for index, name in enumerate(raw_names)}
        elif isinstance(raw_names, dict):
            actual_names = {int(index): str(name) for index, name in raw_names.items()}
        else:
            logger.warning("Model %s does not expose class labels; using configured labels", self._config.model_path)
            return

        self._available_class_ids = set(actual_names)
        validated_weapons: set[int] = set()
        for class_id in self._config.weapon_classes:
            expected = self._config.CLASS_NAMES.get(class_id)
            actual = actual_names.get(class_id)
            if expected and actual and self._normalize_label(expected) == self._normalize_label(actual):
                validated_weapons.add(class_id)
            else:
                logger.warning(
                    "Configured weapon class id=%s label=%r does not match model label=%r; class disabled",
                    class_id,
                    expected,
                    actual,
                )
        self._validated_weapon_classes = validated_weapons
        self._class_names.update(actual_names)

    @staticmethod
    def _normalize_label(value: str) -> str:
        return " ".join(str(value).strip().lower().replace("_", " ").split())

    def get_capabilities(self) -> dict:
        model_available = Path(self._config.model_path).is_file()
        target_ids = set(self._config.target_classes)
        if self._available_class_ids is not None:
            target_ids &= self._available_class_ids
        weapon_ids = (
            set(self._config.weapon_classes)
            if self._validated_weapon_classes is None
            else set(self._validated_weapon_classes)
        )
        weapon_ids &= target_ids
        return {
            "model_name": self._config.model_path,
            "detector_available": model_available,
            "loaded": self._model is not None,
            "availability": (
                "ready" if self._model is not None else "configured_not_loaded" if model_available else "unavailable"
            ),
            "unavailable_reason": self._model_load_error if not model_available else self._model_load_error,
            "supported_classes": [
                self._class_names.get(class_id, f"class_{class_id}")
                for class_id in sorted(target_ids)
            ],
            "weapon_classes": [
                self._class_names.get(class_id, f"class_{class_id}")
                for class_id in sorted(weapon_ids)
            ],
            "weapon_detection_supported": model_available and bool(weapon_ids),
            "class_mapping_validation": (
                "configured_not_loaded"
                if self._available_class_ids is None
                else "validated"
            ),
        }
    
    def detect(
        self,
        frame: np.ndarray,
        confidence_threshold: Optional[float] = None,
        classes: Optional[Tuple[int, ...]] = None
    ) -> List[Detection]:
        """
        Perform object detection on a single frame.
        
        Args:
            frame: Input image as numpy array (BGR format, HWC layout)
            confidence_threshold: Override default confidence threshold
            classes: Override default target classes
            
        Returns:
            List of Detection objects for valid detections
            
        Note:
            Only returns detections for configured target classes
            (persons and vehicles by default).
        """
        # Use configured values if not overridden
        explicit_threshold = confidence_threshold is not None
        conf_thresh = self._config.confidence_threshold if confidence_threshold is None else confidence_threshold
        target_classes = classes or self._config.target_classes
        model = self.model
        if self._available_class_ids is not None:
            target_classes = tuple(class_id for class_id in target_classes if class_id in self._available_class_ids)
        weapon_classes = (
            set(self._config.weapon_classes)
            if self._validated_weapon_classes is None
            else self._validated_weapon_classes
        )
        includes_weapon_classes = bool(set(target_classes) & weapon_classes)
        weapon_threshold = conf_thresh if explicit_threshold else self._config.weapon_confidence_threshold
        inference_threshold = min(conf_thresh, weapon_threshold) if includes_weapon_classes else conf_thresh
        
        # Run inference with optimizations
        results = model.predict(
            source=frame,
            conf=inference_threshold,
            iou=self._config.nms_threshold,
            classes=list(target_classes),
            imgsz=self._config.image_size,
            device=self._device if self._device else None,
            half=getattr(self._config, 'half_precision', False),  # FP16 optimization
            verbose=False  # Suppress per-frame logging
        )

        
        # Parse results into standardized format
        detections = []
        
        for result in results:
            if result.boxes is None or len(result.boxes) == 0:
                continue
                
            boxes = result.boxes
            
            for i in range(len(boxes)):
                # Extract bounding box coordinates
                xyxy = boxes.xyxy[i].cpu().numpy()
                x1, y1, x2, y2 = map(int, xyxy)
                
                # Extract confidence and class
                conf = float(boxes.conf[i].cpu().numpy())
                cls_id = int(boxes.cls[i].cpu().numpy())
                
                # Get class name
                cls_name = self._class_names.get(cls_id, f"class_{cls_id}")
                
                # Classify object category
                is_person = (cls_id == 0)
                is_weapon = cls_id in weapon_classes
                is_animal = (cls_id in self._config.animal_classes)
                is_vehicle = cls_id in (2, 3, 5, 7)
                class_threshold = weapon_threshold if is_weapon else conf_thresh
                if conf < class_threshold:
                    continue
                
                if is_person:
                    category = "person"
                elif is_weapon:
                    category = "weapon"
                elif is_animal:
                    category = "animal"
                elif is_vehicle:
                    category = "vehicle"
                else:
                    category = "generic"
                
                detection = Detection(
                    bbox=(x1, y1, x2, y2),
                    confidence=conf,
                    class_id=cls_id,
                    class_name=cls_name,
                    object_category=category,
                    is_weapon=is_weapon,
                    is_person=is_person,
                    is_vehicle=is_vehicle,
                    is_animal=is_animal,
                    model_source=self._config.model_path,
                    source_class_id=cls_id,
                )
                detections.append(detection)
        
        logger.debug(f"Detected {len(detections)} objects in frame")
        return detections
    
    def detect_batch(
        self,
        frames: List[np.ndarray],
        confidence_threshold: Optional[float] = None
    ) -> List[List[Detection]]:
        """
        Perform object detection on a batch of frames.
        
        More efficient than calling detect() multiple times
        when processing pre-loaded frames.
        
        Args:
            frames: List of input images as numpy arrays
            confidence_threshold: Override default confidence threshold
            
        Returns:
            List of detection lists, one per input frame
        """
        explicit_threshold = confidence_threshold is not None
        conf_thresh = self._config.confidence_threshold if confidence_threshold is None else confidence_threshold
        model = self.model
        target_classes = self._config.target_classes
        if self._available_class_ids is not None:
            target_classes = tuple(class_id for class_id in target_classes if class_id in self._available_class_ids)
        weapon_classes = (
            set(self._config.weapon_classes)
            if self._validated_weapon_classes is None
            else self._validated_weapon_classes
        )
        includes_weapon_classes = bool(set(target_classes) & weapon_classes)
        weapon_threshold = conf_thresh if explicit_threshold else self._config.weapon_confidence_threshold
        inference_threshold = min(conf_thresh, weapon_threshold) if includes_weapon_classes else conf_thresh
        
        # Run batch inference
        results = model.predict(
            source=frames,
            conf=inference_threshold,
            iou=self._config.nms_threshold,
            classes=list(target_classes),
            imgsz=self._config.image_size,
            device=self._device if self._device else None,
            verbose=False
        )
        
        # Parse each result
        all_detections = []
        
        for result in results:
            frame_detections = []
            
            if result.boxes is not None and len(result.boxes) > 0:
                boxes = result.boxes
                
                for i in range(len(boxes)):
                    xyxy = boxes.xyxy[i].cpu().numpy()
                    x1, y1, x2, y2 = map(int, xyxy)
                    conf = float(boxes.conf[i].cpu().numpy())
                    cls_id = int(boxes.cls[i].cpu().numpy())
                    cls_name = self._class_names.get(cls_id, f"class_{cls_id}")
                    is_person = cls_id == 0
                    is_weapon = cls_id in weapon_classes
                    is_animal = cls_id in self._config.animal_classes
                    is_vehicle = cls_id in (2, 3, 5, 7)
                    class_threshold = weapon_threshold if is_weapon else conf_thresh
                    if conf < class_threshold:
                        continue
                    if is_person:
                        category = "person"
                    elif is_weapon:
                        category = "weapon"
                    elif is_animal:
                        category = "animal"
                    elif is_vehicle:
                        category = "vehicle"
                    else:
                        category = "generic"
                    
                    detection = Detection(
                        bbox=(x1, y1, x2, y2),
                        confidence=conf,
                        class_id=cls_id,
                        class_name=cls_name,
                        object_category=category,
                        is_weapon=is_weapon,
                        is_person=is_person,
                        is_vehicle=is_vehicle,
                        is_animal=is_animal,
                        model_source=self._config.model_path,
                        source_class_id=cls_id,
                    )
                    frame_detections.append(detection)
            
            all_detections.append(frame_detections)
        
        logger.debug(f"Batch detection complete: {len(all_detections)} frames processed")
        return all_detections
    
    def get_class_name(self, class_id: int) -> str:
        """
        Get human-readable name for a class ID.
        
        Args:
            class_id: COCO class identifier
            
        Returns:
            Class name string
        """
        return self._class_names.get(class_id, f"Unknown ({class_id})")
    
    def warmup(self, image_size: Optional[Tuple[int, int]] = None) -> None:
        """
        Perform a warmup inference to initialize CUDA kernels.
        
        Call this before starting real-time processing to avoid
        latency spikes on the first frame.
        
        Args:
            image_size: Optional (height, width) for warmup image
        """
        if image_size is None:
            h = w = self._config.image_size
        else:
            h, w = image_size
        
        # Create dummy image
        dummy_frame = np.zeros((h, w, 3), dtype=np.uint8)
        
        logger.info("Performing detector warmup...")
        _ = self.detect(dummy_frame)
        logger.info("Detector warmup complete")
    
    def __repr__(self) -> str:
        return (
            f"YOLODetector(model={self._config.model_path}, "
            f"conf={self._config.confidence_threshold}, "
            f"classes={self._config.target_classes})"
        )
