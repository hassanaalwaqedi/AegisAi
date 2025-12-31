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
    """
    bbox: Tuple[int, int, int, int]
    confidence: float
    class_id: int
    class_name: str


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
            logger.info(f"Loading YOLO model: {self._config.model_path}")
            self._model = YOLO(self._config.model_path)
            
            # Log device information
            if hasattr(self._model, 'device'):
                logger.info(f"Model loaded on device: {self._model.device}")
        
        return self._model
    
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
        conf_thresh = confidence_threshold or self._config.confidence_threshold
        target_classes = classes or self._config.target_classes
        
        # Run inference with optimizations
        results = self.model.predict(
            source=frame,
            conf=conf_thresh,
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
                
                detection = Detection(
                    bbox=(x1, y1, x2, y2),
                    confidence=conf,
                    class_id=cls_id,
                    class_name=cls_name
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
        conf_thresh = confidence_threshold or self._config.confidence_threshold
        
        # Run batch inference
        results = self.model.predict(
            source=frames,
            conf=conf_thresh,
            iou=self._config.nms_threshold,
            classes=list(self._config.target_classes),
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
                    
                    detection = Detection(
                        bbox=(x1, y1, x2, y2),
                        confidence=conf,
                        class_id=cls_id,
                        class_name=cls_name
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
