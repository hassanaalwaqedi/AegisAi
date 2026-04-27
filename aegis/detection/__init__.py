"""
AegisAI Detection Module

Provides object detection capabilities using YOLO models.
Phase 1 uses YOLO11n (nano) for CPU-optimized inference.
"""

from aegis.detection.yolo_detector import YOLODetector, Detection

__all__ = ["YOLODetector", "Detection"]
