"""
AegisAI - Abstract Interfaces for Modular AI Pipeline

Defines the contracts for all pluggable AI modules.
Phase 1 implements Detector, Tracker, and RiskEngine.
Phase 2/3 modules implement the remaining interfaces.

This enables clean separation between edge (CPU) and cloud (GPU) layers,
and allows swapping implementations without changing the pipeline.

Architecture:
    Phase 1 (CPU):  BaseDetector, BaseTracker, BaseRiskEngine
    Phase 2 (GPU):  BaseSegmenter, BaseVerifier, BaseDepthEstimator
    Phase 3 (Adv):  BasePoseEstimator, BaseActionRecognizer
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


# ═══════════════════════════════════════════════════════════════════════
# PHASE 1 INTERFACES (CPU - Edge Layer)
# ═══════════════════════════════════════════════════════════════════════


class BaseDetector(ABC):
    """
    Abstract base class for object detection models.

    All detectors must return a list of Detection-like objects with at minimum:
    bbox, confidence, class_id, class_name.

    Implementations:
        - YOLODetector (Phase 1, CPU)
        - Future: custom weapon-specific detectors
    """

    @abstractmethod
    def detect(self, frame: np.ndarray, **kwargs) -> list:
        """
        Detect objects in a single frame.

        Args:
            frame: Input image as numpy array (BGR, HWC)

        Returns:
            List of detection objects with bbox, confidence, class_id, class_name
        """
        ...

    @abstractmethod
    def warmup(self, image_size: Optional[Tuple[int, int]] = None) -> None:
        """Perform warmup inference to initialize model internals."""
        ...


class BaseTracker(ABC):
    """
    Abstract base class for multi-object trackers.

    Trackers receive detections per-frame and assign stable IDs.

    Implementations:
        - ByteTrackTracker (Phase 1, CPU, IoU-based)
        - DeepSORTTracker (legacy, appearance-based)
    """

    @abstractmethod
    def update(self, detections: list, frame: np.ndarray) -> list:
        """
        Update tracker with new detections.

        Args:
            detections: List of Detection objects from current frame
            frame: Current video frame

        Returns:
            List of Track objects with stable track_id assignments
        """
        ...

    @abstractmethod
    def get_track_count(self) -> int:
        """Get current number of active confirmed tracks."""
        ...

    @abstractmethod
    def reset(self) -> None:
        """Reset all tracker state."""
        ...


class BaseRiskEngine(ABC):
    """
    Abstract base class for risk assessment engines.

    Risk engines evaluate tracked objects and determine threat levels.

    Implementations:
        - ProximityRiskEngine (Phase 1, rule-based, CPU)
        - RiskEngine (Phase 3, behavior-based, requires analysis layer)
    """

    @abstractmethod
    def assess(self, tracks: list, frame_id: int, **kwargs) -> Any:
        """
        Assess risk for a set of tracked objects.

        Args:
            tracks: List of Track objects from tracker
            frame_id: Current frame number

        Returns:
            Risk assessment result (implementation-specific)
        """
        ...

    @abstractmethod
    def get_stats(self) -> dict:
        """Get engine statistics."""
        ...

    @abstractmethod
    def reset(self) -> None:
        """Reset engine state."""
        ...


# ═══════════════════════════════════════════════════════════════════════
# PHASE 2 INTERFACES (GPU - Cloud Layer)
# ═══════════════════════════════════════════════════════════════════════


class BaseSegmenter(ABC):
    """
    Abstract base class for segmentation models.

    Phase 2: SAM / MobileSAM for precise object masks.
    Used to determine weapon-holding confidence via mask overlap.

    Implementations:
        - SAMSegmenter (Phase 2, GPU)
    """

    @abstractmethod
    def segment(
        self,
        frame: np.ndarray,
        bbox: Tuple[int, int, int, int],
        **kwargs
    ) -> np.ndarray:
        """
        Segment an object within a bounding box.

        Args:
            frame: Input image
            bbox: Bounding box (x1, y1, x2, y2) to segment within

        Returns:
            Binary mask (H, W) of the segmented object
        """
        ...


class BaseVerifier(ABC):
    """
    Abstract base class for vision-language verification models.

    Phase 2: CLIP for semantic validation of detected threats.
    Verifies edge detections using natural language prompts.

    Implementations:
        - CLIPVerifier (Phase 2, GPU)
    """

    @abstractmethod
    def verify(
        self,
        frame: np.ndarray,
        prompt: str,
        bbox: Optional[Tuple[int, int, int, int]] = None,
    ) -> float:
        """
        Verify a visual concept using natural language.

        Args:
            frame: Input image
            prompt: Description to verify (e.g., "person holding a gun")
            bbox: Optional region to focus on

        Returns:
            Confidence score (0.0 - 1.0) that the prompt matches
        """
        ...


class BaseDepthEstimator(ABC):
    """
    Abstract base class for monocular depth estimation.

    Phase 2: MiDaS for estimating 3D distances between objects.

    Implementations:
        - MiDaSEstimator (Phase 2, GPU)
    """

    @abstractmethod
    def estimate(self, frame: np.ndarray) -> np.ndarray:
        """
        Estimate depth map from a single frame.

        Args:
            frame: Input image (BGR, HWC)

        Returns:
            Depth map as float32 array (H, W), values in relative depth
        """
        ...


# ═══════════════════════════════════════════════════════════════════════
# PHASE 3 INTERFACES (Advanced / Enterprise)
# ═══════════════════════════════════════════════════════════════════════


class BasePoseEstimator(ABC):
    """
    Abstract base class for human pose estimation.

    Phase 3: MediaPipe or similar for body keypoint detection.
    Useful for identifying threatening postures.

    Implementations:
        - MediaPipePose (Phase 3, GPU or CPU)
    """

    @abstractmethod
    def estimate(
        self,
        frame: np.ndarray,
        bbox: Optional[Tuple[int, int, int, int]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Estimate human pose keypoints.

        Args:
            frame: Input image
            bbox: Optional person bounding box

        Returns:
            List of keypoint dicts with name, position, confidence
        """
        ...


class BaseActionRecognizer(ABC):
    """
    Abstract base class for action recognition.

    Phase 3: SlowFast or similar for classifying actions
    (walking, running, aiming, attacking).

    Implementations:
        - SlowFastRecognizer (Phase 3, GPU)
    """

    @abstractmethod
    def recognize(
        self,
        frames: List[np.ndarray],
        bbox: Optional[Tuple[int, int, int, int]] = None,
    ) -> Dict[str, float]:
        """
        Recognize action from a sequence of frames.

        Args:
            frames: List of consecutive frames (temporal window)
            bbox: Optional person bounding box

        Returns:
            Dict mapping action names to confidence scores
        """
        ...
