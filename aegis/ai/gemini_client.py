"""
AegisAI - Google Gemini Client

Provides AI/LLM capabilities using Google Gemini API with Flash mode.
Replaces OpenAI integration with faster, more cost-effective Gemini Flash model.

Features:
- Gemini Flash mode for fast responses
- Structured output parsing
- Error handling and retries
- Token usage tracking

Copyright 2024 AegisAI Project
"""

import os
import json
import logging
import time
from typing import Optional, Dict, List, Any, Union
from dataclasses import dataclass, field
from functools import lru_cache

import requests

logger = logging.getLogger(__name__)


@dataclass
class GeminiConfig:
    """Configuration for Gemini API client."""
    api_key: str
    model: str = "gemini-2.0-flash-exp"
    max_tokens: int = 2048
    temperature: float = 0.7
    timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0


@dataclass
class GeminiResponse:
    """Response from Gemini API."""
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    finish_reason: str = "stop"
    latency_ms: float = 0.0
    raw_response: Dict = field(default_factory=dict)


class GeminiError(Exception):
    """Base exception for Gemini API errors."""
    pass


class GeminiAPIError(GeminiError):
    """API-level error from Gemini."""
    def __init__(self, message: str, status_code: int = 0, response: Dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response or {}


class GeminiClient:
    """
    Google Gemini API client with Flash mode support.
    
    Example:
        >>> client = GeminiClient("your-api-key")
        >>> response = client.generate("What is AegisAI?")
        >>> print(response.text)
    """
    
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
    
    def __init__(self, config: Optional[GeminiConfig] = None):
        """
        Initialize Gemini client.
        
        Args:
            config: Optional GeminiConfig, loads from env if not provided
        """
        if config:
            self.config = config
        else:
            self.config = self._load_config_from_env()
        
        self._validate_config()
        self._total_tokens_used = 0
        self._request_count = 0
        
        logger.info(f"GeminiClient initialized with model: {self.config.model}")
    
    def _load_config_from_env(self) -> GeminiConfig:
        """Load configuration from environment variables."""
        api_key = os.getenv("GEMINI_API_KEY", "")
        
        return GeminiConfig(
            api_key=api_key,
            model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp"),
            max_tokens=int(os.getenv("GEMINI_MAX_TOKENS", "2048")),
            temperature=float(os.getenv("GEMINI_TEMPERATURE", "0.7")),
        )
    
    def _validate_config(self) -> None:
        """Validate configuration."""
        if not self.config.api_key:
            raise GeminiError("GEMINI_API_KEY not set. Please set it in .env file.")
    
    def _get_endpoint(self, action: str = "generateContent") -> str:
        """Get the API endpoint URL."""
        return f"{self.BASE_URL}/{self.config.model}:{action}?key={self.config.api_key}"
    
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False
    ) -> GeminiResponse:
        """
        Generate text using Gemini Flash.
        
        Args:
            prompt: User prompt
            system_prompt: Optional system instructions
            temperature: Override default temperature
            max_tokens: Override max output tokens
            json_mode: If True, request JSON output
            
        Returns:
            GeminiResponse with generated text
        """
        start_time = time.time()
        
        # Build request body
        contents = []
        
        # Add system instruction if provided
        if system_prompt:
            contents.append({
                "role": "user",
                "parts": [{"text": f"System: {system_prompt}"}]
            })
            contents.append({
                "role": "model",
                "parts": [{"text": "Understood. I will follow these instructions."}]
            })
        
        # Add user prompt
        contents.append({
            "role": "user",
            "parts": [{"text": prompt}]
        })
        
        # Request body
        body = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature or self.config.temperature,
                "maxOutputTokens": max_tokens or self.config.max_tokens,
                "topP": 0.95,
                "topK": 40
            }
        }
        
        # Add JSON mode hint
        if json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"
        
        # Make request with retries
        response = self._make_request(body)
        
        latency = (time.time() - start_time) * 1000
        self._request_count += 1
        
        # Parse response
        return self._parse_response(response, latency)
    
    def _make_request(self, body: Dict) -> Dict:
        """Make HTTP request with retry logic."""
        endpoint = self._get_endpoint()
        
        for attempt in range(self.config.max_retries):
            try:
                response = requests.post(
                    endpoint,
                    json=body,
                    headers={"Content-Type": "application/json"},
                    timeout=self.config.timeout
                )
                
                if response.status_code == 200:
                    return response.json()
                
                elif response.status_code == 429:
                    # Rate limited - wait and retry
                    wait_time = self.config.retry_delay * (2 ** attempt)
                    logger.warning(f"Rate limited, waiting {wait_time}s before retry")
                    time.sleep(wait_time)
                    continue
                
                elif response.status_code >= 400:
                    error_data = response.json() if response.text else {}
                    error_msg = error_data.get("error", {}).get("message", response.text)
                    raise GeminiAPIError(
                        f"API error: {error_msg}",
                        status_code=response.status_code,
                        response=error_data
                    )
                    
            except requests.exceptions.Timeout:
                logger.warning(f"Request timeout, attempt {attempt + 1}/{self.config.max_retries}")
                if attempt == self.config.max_retries - 1:
                    raise GeminiError("Request timed out after all retries")
                time.sleep(self.config.retry_delay)
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed: {e}")
                raise GeminiError(f"Request failed: {e}")
        
        raise GeminiError("Max retries exceeded")
    
    def _parse_response(self, data: Dict, latency: float) -> GeminiResponse:
        """Parse Gemini API response."""
        try:
            candidates = data.get("candidates", [])
            if not candidates:
                raise GeminiError("No response candidates returned")
            
            candidate = candidates[0]
            content = candidate.get("content", {})
            parts = content.get("parts", [])
            
            text = ""
            for part in parts:
                if "text" in part:
                    text += part["text"]
            
            # Get token usage
            usage = data.get("usageMetadata", {})
            prompt_tokens = usage.get("promptTokenCount", 0)
            completion_tokens = usage.get("candidatesTokenCount", 0)
            total_tokens = usage.get("totalTokenCount", 0)
            
            self._total_tokens_used += total_tokens
            
            return GeminiResponse(
                text=text.strip(),
                model=self.config.model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                finish_reason=candidate.get("finishReason", "STOP"),
                latency_ms=latency,
                raw_response=data
            )
            
        except KeyError as e:
            logger.error(f"Error parsing response: {e}")
            raise GeminiError(f"Failed to parse response: {e}")
    
    def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None
    ) -> Dict:
        """
        Generate structured JSON output.
        
        Args:
            prompt: User prompt (should request JSON format)
            system_prompt: Optional system instructions
            
        Returns:
            Parsed JSON dictionary
        """
        # Add JSON instruction to prompt
        enhanced_prompt = f"{prompt}\n\nRespond with valid JSON only, no markdown or explanation."
        
        response = self.generate(
            prompt=enhanced_prompt,
            system_prompt=system_prompt,
            json_mode=True
        )
        
        try:
            # Clean response if needed
            text = response.text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            logger.debug(f"Raw response: {response.text}")
            raise GeminiError(f"Invalid JSON response: {e}")
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None
    ) -> GeminiResponse:
        """
        Multi-turn chat conversation.
        
        Args:
            messages: List of {"role": "user"|"assistant", "content": "..."}
            system_prompt: Optional system instructions
            
        Returns:
            GeminiResponse
        """
        contents = []
        
        # Add system instruction
        if system_prompt:
            contents.append({
                "role": "user",
                "parts": [{"text": f"System: {system_prompt}"}]
            })
            contents.append({
                "role": "model",
                "parts": [{"text": "Understood."}]
            })
        
        # Convert messages to Gemini format
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({
                "role": role,
                "parts": [{"text": msg["content"]}]
            })
        
        body = {
            "contents": contents,
            "generationConfig": {
                "temperature": self.config.temperature,
                "maxOutputTokens": self.config.max_tokens,
            }
        }
        
        start_time = time.time()
        response = self._make_request(body)
        latency = (time.time() - start_time) * 1000
        
        return self._parse_response(response, latency)
    
    def get_stats(self) -> Dict:
        """Get client usage statistics."""
        return {
            "model": self.config.model,
            "total_tokens_used": self._total_tokens_used,
            "request_count": self._request_count,
            "avg_tokens_per_request": (
                self._total_tokens_used / self._request_count 
                if self._request_count > 0 else 0
            )
        }


# Global singleton
_client: Optional[GeminiClient] = None


def get_gemini_client() -> GeminiClient:
    """Get the global Gemini client instance."""
    global _client
    if _client is None:
        _client = GeminiClient()
    return _client


def generate(prompt: str, system_prompt: Optional[str] = None) -> str:
    """Quick function to generate text."""
    response = get_gemini_client().generate(prompt, system_prompt)
    return response.text


def generate_json(prompt: str, system_prompt: Optional[str] = None) -> Dict:
    """Quick function to generate JSON."""
    return get_gemini_client().generate_json(prompt, system_prompt)
