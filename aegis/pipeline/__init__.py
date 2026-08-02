"""
AegisAI - Pipeline Package

AI processing pipeline with Redis Streams event bus.

Pipeline stages:
    Camera → DetectionStage → TrackingStage → RiskScoringStage → AlertingStage

Each stage runs in its own thread, reads from a Redis stream,
processes messages, and publishes results to the next stream.
"""

from aegis.pipeline.ai_pipeline import AICameraPipeline, DetectionResult
from aegis.pipeline.stages import Pipeline, PipelineStage, Streams
from aegis.pipeline.overlays import draw_analysis_overlay, draw_risk_overlay

__all__ = [
    # Legacy
    "AICameraPipeline",
    "DetectionResult",
    # Pipeline framework
    "Pipeline",
    "PipelineStage",
    "Streams",
    # Overlays
    "draw_analysis_overlay",
    "draw_risk_overlay",
]
