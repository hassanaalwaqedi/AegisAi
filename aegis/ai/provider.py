"""
AegisAI - Abstract LLM Provider Interface

Decouples the AI orchestrator from any specific LLM vendor.
GeminiFlashProvider is the first implementation.

To add a new provider (e.g. OpenAI, Groq, Claude):
  1. Create a class that inherits LLMProvider
  2. Implement generate() and generate_json()
  3. Pass it to AIOrchestrator(provider=YourProvider())

The frontend and orchestrator logic never change when switching providers.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared response type
# ---------------------------------------------------------------------------

@dataclass
class LLMResponse:
    """Vendor-agnostic LLM response."""
    text: str
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    finish_reason: str = "stop"
    raw: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class LLMProvider(ABC):
    """
    Abstract interface for LLM providers.

    All business logic in the orchestrator uses this interface.
    No provider-specific code should leak outside the provider class.
    """

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Generate a text response from a prompt."""
        ...

    @abstractmethod
    def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a structured JSON response."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the model identifier string."""
        ...

    def is_available(self) -> bool:
        """Check if the provider is reachable. Override for health checks."""
        return True


# ---------------------------------------------------------------------------
# Gemini Flash Provider (current implementation)
# ---------------------------------------------------------------------------

class GeminiFlashProvider(LLMProvider):
    """
    Google Gemini 2.5 Flash implementation of LLMProvider.

    Wraps the existing GeminiClient with the abstract interface.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        import os
        from aegis.ai.gemini_client import GeminiClient, GeminiConfig

        resolved_key = api_key or os.getenv("GEMINI_API_KEY", "")
        resolved_model = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

        self._client = GeminiClient(GeminiConfig(
            api_key=resolved_key,
            model=resolved_model,
            temperature=0.3,
            max_tokens=1500,
        ))
        self._model = resolved_model
        logger.info("GeminiFlashProvider initialized: model=%s", resolved_model)

    @property
    def model_name(self) -> str:
        return self._model

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        resp = self._client.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
        )
        return LLMResponse(
            text=resp.text,
            model=resp.model,
            prompt_tokens=resp.prompt_tokens,
            completion_tokens=resp.completion_tokens,
            total_tokens=resp.total_tokens,
            latency_ms=resp.latency_ms,
            finish_reason=resp.finish_reason,
            raw=resp.raw_response,
        )

    def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._client.generate_json(prompt=prompt, system_prompt=system_prompt)

    def is_available(self) -> bool:
        try:
            resp = self._client.generate("ping", max_tokens=5)
            return bool(resp.text)
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Null / fallback provider (for testing without API key)
# ---------------------------------------------------------------------------

class FallbackProvider(LLMProvider):
    """
    Returns a canned response when no real provider is available.
    Ensures the platform keeps running even without an LLM API key.
    """

    @property
    def model_name(self) -> str:
        return "fallback-no-llm"

    def generate(self, prompt: str, **kwargs) -> LLMResponse:
        return LLMResponse(
            text="I couldn't reach the AI service. The platform continues to operate normally.",
            model=self.model_name,
        )

    def generate_json(self, prompt: str, **kwargs) -> Dict[str, Any]:
        return {
            "intent": "General",
            "answer": "I couldn't reach the AI service. The platform continues to operate normally.",
            "actions": [],
            "sources": [],
            "confidence": 0.0,
        }


# ---------------------------------------------------------------------------
# Provider factory
# ---------------------------------------------------------------------------

def get_default_provider() -> LLMProvider:
    """
    Return the best available LLM provider.
    Falls back gracefully if no API key is configured.
    """
    import os
    api_key = os.getenv("GEMINI_API_KEY", "")
    if api_key:
        try:
            return GeminiFlashProvider(api_key=api_key)
        except Exception as exc:
            logger.warning("GeminiFlashProvider init failed: %s — using fallback", exc)
    else:
        logger.warning("GEMINI_API_KEY not set — using FallbackProvider")
    return FallbackProvider()
