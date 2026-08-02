"""
AegisAI - AI Module

AI Security Copilot powered by Gemini 2.5 Flash.

Architecture:
    Frontend → FastAPI AI Orchestrator → Collect Context → Gemini → Structured Response → Frontend

Gemini never talks directly to the frontend or queries the database.
"""

from aegis.ai.gemini_client import GeminiClient, get_gemini_client
from aegis.ai.orchestrator import AIOrchestrator, get_orchestrator
from aegis.ai.schemas import ChatRequest, ChatResponse, Intent

__all__ = [
    "GeminiClient",
    "get_gemini_client",
    "AIOrchestrator",
    "get_orchestrator",
    "ChatRequest",
    "ChatResponse",
    "Intent",
]
