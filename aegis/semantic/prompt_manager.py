"""
AegisAI - Prompt Manager
Text Prompt Management with Caching

This module manages semantic prompts with priority ordering
and TTL-based caching for repeated query optimization.

Features:
- LRU cache with configurable TTL
- Priority-based prompt ordering
- Image hashing for cache keys
"""

import hashlib
import logging
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from aegis.semantic.dino_engine import SemanticDetection

# Configure module logger
logger = logging.getLogger(__name__)


@dataclass
class Prompt:
    """
    Semantic prompt container.
    
    Attributes:
        prompt_id: Unique identifier
        text: The prompt text
        priority: Ordering priority (higher = more important)
        created_at: Timestamp when prompt was added
        expires_at: Optional expiration timestamp
    """
    prompt_id: str
    text: str
    priority: int = 0
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    
    def is_expired(self) -> bool:
        """Check if prompt has expired."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at


@dataclass
class CacheEntry:
    """Cache entry for prompt results."""
    result: List[SemanticDetection]
    timestamp: float
    
    def is_expired(self, ttl: int) -> bool:
        """Check if cache entry has expired."""
        return time.time() - self.timestamp > ttl


class PromptManager:
    """
    Manages semantic prompts with TTL-based caching.
    
    Provides prompt storage, priority ordering, and result caching
    to optimize repeated semantic queries.
    
    Attributes:
        cache_ttl: Time-to-live for cached results in seconds
        
    Example:
        >>> manager = PromptManager(cache_ttl=60)
        >>> prompt_id = manager.add_prompt("person with bag", priority=1)
        >>> prompts = manager.get_active_prompts()
    """
    
    def __init__(self, cache_ttl: int = 60, max_cache_size: int = 100):
        """
        Initialize the prompt manager.
        
        Args:
            cache_ttl: Time-to-live for cached results in seconds
            max_cache_size: Maximum number of cached results
        """
        self._cache_ttl = cache_ttl
        self._max_cache_size = max_cache_size
        self._prompts: Dict[str, Prompt] = {}
        self._result_cache: OrderedDict[str, CacheEntry] = OrderedDict()
        
        logger.info(f"PromptManager initialized with TTL={cache_ttl}s")
    
    def add_prompt(
        self,
        text: str,
        priority: int = 0,
        ttl: Optional[int] = None
    ) -> str:
        """
        Add a semantic prompt.
        
        Args:
            text: The prompt text
            priority: Ordering priority (higher = more important)
            ttl: Optional TTL for this prompt (None = no expiry)
            
        Returns:
            Unique prompt ID
        """
        prompt_id = str(uuid.uuid4())[:8]
        expires_at = time.time() + ttl if ttl else None
        
        prompt = Prompt(
            prompt_id=prompt_id,
            text=text.strip(),
            priority=priority,
            expires_at=expires_at
        )
        
        self._prompts[prompt_id] = prompt
        logger.info(f"Added prompt '{text}' with ID {prompt_id}")
        return prompt_id
    
    def remove_prompt(self, prompt_id: str) -> bool:
        """
        Remove a prompt by ID.
        
        Args:
            prompt_id: The prompt identifier
            
        Returns:
            True if prompt was removed, False if not found
        """
        if prompt_id in self._prompts:
            del self._prompts[prompt_id]
            logger.info(f"Removed prompt {prompt_id}")
            return True
        return False
    
    def get_prompt(self, prompt_id: str) -> Optional[Prompt]:
        """Get a prompt by ID."""
        return self._prompts.get(prompt_id)
    
    def get_active_prompts(self) -> List[Prompt]:
        """
        Get all active (non-expired) prompts, sorted by priority.
        
        Returns:
            List of Prompt objects, highest priority first
        """
        # Clean expired prompts
        self._cleanup_expired_prompts()
        
        # Sort by priority (descending)
        active = list(self._prompts.values())
        active.sort(key=lambda p: p.priority, reverse=True)
        return active
    
    def _cleanup_expired_prompts(self) -> int:
        """Remove expired prompts. Returns count removed."""
        expired = [pid for pid, p in self._prompts.items() if p.is_expired()]
        for pid in expired:
            del self._prompts[pid]
        if expired:
            logger.debug(f"Cleaned up {len(expired)} expired prompts")
        return len(expired)
    
    # ═══════════════════════════════════════════════════════════
    # RESULT CACHING
    # ═══════════════════════════════════════════════════════════
    
    @staticmethod
    def compute_image_hash(image) -> str:
        """
        Compute a fast hash of an image for cache keys.
        
        Uses downsampled image data for speed.
        
        Args:
            image: numpy array image
            
        Returns:
            Hex hash string
        """
        import numpy as np
        
        # Downsample to 64x64 for fast hashing
        if image.size > 64 * 64 * 3:
            # Simple downsampling by slicing
            h, w = image.shape[:2]
            step_h = max(1, h // 64)
            step_w = max(1, w // 64)
            small = image[::step_h, ::step_w, :]
        else:
            small = image
        
        # Compute hash
        return hashlib.md5(small.tobytes()).hexdigest()[:16]
    
    def _make_cache_key(self, prompt: str, image_hash: str) -> str:
        """Create cache key from prompt and image hash."""
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:8]
        return f"{prompt_hash}_{image_hash}"
    
    def get_cached_result(
        self,
        prompt: str,
        image_hash: str
    ) -> Optional[List[SemanticDetection]]:
        """
        Get cached result for a prompt and image.
        
        Args:
            prompt: The prompt text
            image_hash: Hash of the input image
            
        Returns:
            Cached detections if found and not expired, None otherwise
        """
        cache_key = self._make_cache_key(prompt, image_hash)
        entry = self._result_cache.get(cache_key)
        
        if entry is None:
            return None
        
        if entry.is_expired(self._cache_ttl):
            del self._result_cache[cache_key]
            return None
        
        logger.debug(f"Cache hit for prompt '{prompt[:20]}...'")
        return entry.result
    
    def cache_result(
        self,
        prompt: str,
        image_hash: str,
        result: List[SemanticDetection]
    ) -> None:
        """
        Cache a result for a prompt and image.
        
        Args:
            prompt: The prompt text
            image_hash: Hash of the input image
            result: The semantic detections to cache
        """
        # Enforce max cache size (LRU)
        while len(self._result_cache) >= self._max_cache_size:
            self._result_cache.popitem(last=False)
        
        cache_key = self._make_cache_key(prompt, image_hash)
        self._result_cache[cache_key] = CacheEntry(
            result=result,
            timestamp=time.time()
        )
        logger.debug(f"Cached result for prompt '{prompt[:20]}...'")
    
    def clear_cache(self) -> int:
        """Clear all cached results. Returns count cleared."""
        count = len(self._result_cache)
        self._result_cache.clear()
        logger.info(f"Cleared {count} cached results")
        return count
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        expired = sum(
            1 for e in self._result_cache.values()
            if e.is_expired(self._cache_ttl)
        )
        return {
            "total_prompts": len(self._prompts),
            "cached_results": len(self._result_cache),
            "expired_entries": expired,
            "cache_ttl": self._cache_ttl
        }
    
    def __repr__(self) -> str:
        return (
            f"PromptManager(prompts={len(self._prompts)}, "
            f"cached={len(self._result_cache)}, "
            f"ttl={self._cache_ttl}s)"
        )
