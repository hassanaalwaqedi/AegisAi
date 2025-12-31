"""
AegisAI - Semantic Layer Module
Grounding DINO Integration for Language-Guided Scene Understanding

This module provides semantic reasoning capabilities powered by Grounding DINO,
enabling natural language queries against detected objects in real-time video.

Key Features:
- Event-driven DINO inference (no per-frame processing)
- Async non-blocking execution
- Prompt caching for repeated queries
- Fusion with YOLO detection and tracking

Usage:
    from aegis.semantic import DinoEngine, SemanticTrigger, SemanticFusion
    
    engine = DinoEngine(config.semantic)
    trigger = SemanticTrigger(config.semantic)
    fusion = SemanticFusion()
"""

from aegis.semantic.dino_engine import DinoEngine, SemanticDetection
from aegis.semantic.prompt_manager import PromptManager, Prompt
from aegis.semantic.semantic_trigger import SemanticTrigger, TriggerEvent, TriggerType
from aegis.semantic.semantic_fusion import SemanticFusion, UnifiedObjectIntelligence
from aegis.semantic.async_executor import SemanticExecutor

__all__ = [
    # Engine
    "DinoEngine",
    "SemanticDetection",
    # Prompts
    "PromptManager",
    "Prompt",
    # Triggers
    "SemanticTrigger",
    "TriggerEvent",
    "TriggerType",
    # Fusion
    "SemanticFusion",
    "UnifiedObjectIntelligence",
    # Executor
    "SemanticExecutor",
]
