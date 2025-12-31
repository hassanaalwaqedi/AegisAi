"""
AegisAI - Prompt Manager Unit Tests

Tests for prompt caching and management.
"""

import pytest
import time
import numpy as np
from unittest.mock import MagicMock

from aegis.semantic.prompt_manager import (
    PromptManager,
    Prompt,
    CacheEntry
)
from aegis.semantic.dino_engine import SemanticDetection


class TestPromptManager:
    """Tests for PromptManager class."""
    
    @pytest.fixture
    def manager(self):
        """Create prompt manager."""
        return PromptManager(cache_ttl=60, max_cache_size=100)
    
    def test_add_prompt(self, manager):
        """Should add prompts successfully."""
        prompt_id = manager.add_prompt("person with bag", priority=5)
        
        assert prompt_id is not None
        assert len(prompt_id) == 8
        
        prompt = manager.get_prompt(prompt_id)
        assert prompt.text == "person with bag"
        assert prompt.priority == 5
    
    def test_remove_prompt(self, manager):
        """Should remove prompts by ID."""
        prompt_id = manager.add_prompt("test prompt")
        
        success = manager.remove_prompt(prompt_id)
        assert success is True
        
        prompt = manager.get_prompt(prompt_id)
        assert prompt is None
    
    def test_remove_nonexistent_prompt(self, manager):
        """Should return False for nonexistent prompts."""
        success = manager.remove_prompt("nonexistent")
        assert success is False
    
    def test_get_active_prompts_sorted_by_priority(self, manager):
        """Active prompts should be sorted by priority."""
        manager.add_prompt("low priority", priority=1)
        manager.add_prompt("high priority", priority=10)
        manager.add_prompt("medium priority", priority=5)
        
        active = manager.get_active_prompts()
        
        assert len(active) == 3
        assert active[0].text == "high priority"
        assert active[1].text == "medium priority"
        assert active[2].text == "low priority"
    
    def test_image_hash_computation(self, manager):
        """Should compute consistent image hashes."""
        image = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        
        hash1 = manager.compute_image_hash(image)
        hash2 = manager.compute_image_hash(image)
        
        assert hash1 == hash2
        assert len(hash1) == 16
    
    def test_cache_result(self, manager):
        """Should cache and retrieve results."""
        prompt = "test prompt"
        image_hash = "abc123"
        detections = [
            SemanticDetection(
                bbox=(10, 10, 50, 50),
                confidence=0.8,
                phrase="test",
                matched_text=prompt
            )
        ]
        
        manager.cache_result(prompt, image_hash, detections)
        
        cached = manager.get_cached_result(prompt, image_hash)
        
        assert cached is not None
        assert len(cached) == 1
        assert cached[0].confidence == 0.8
    
    def test_cache_miss(self, manager):
        """Should return None for cache miss."""
        cached = manager.get_cached_result("unknown prompt", "unknown_hash")
        assert cached is None
    
    def test_cache_clear(self, manager):
        """Should clear all cached results."""
        manager.cache_result("prompt1", "hash1", [])
        manager.cache_result("prompt2", "hash2", [])
        
        count = manager.clear_cache()
        
        assert count == 2
        assert manager.get_cached_result("prompt1", "hash1") is None
    
    def test_cache_stats(self, manager):
        """Should return correct cache statistics."""
        manager.add_prompt("prompt1")
        manager.cache_result("prompt1", "hash1", [])
        
        stats = manager.get_cache_stats()
        
        assert stats["total_prompts"] == 1
        assert stats["cached_results"] == 1
        assert stats["cache_ttl"] == 60


class TestPrompt:
    """Tests for Prompt dataclass."""
    
    def test_prompt_not_expired(self):
        """Prompt without expiry should not be expired."""
        prompt = Prompt(
            prompt_id="test123",
            text="test prompt",
            priority=0
        )
        
        assert prompt.is_expired() is False
    
    def test_prompt_with_future_expiry(self):
        """Prompt with future expiry should not be expired."""
        prompt = Prompt(
            prompt_id="test123",
            text="test prompt",
            expires_at=time.time() + 3600  # 1 hour from now
        )
        
        assert prompt.is_expired() is False


class TestCacheEntry:
    """Tests for CacheEntry dataclass."""
    
    def test_not_expired_within_ttl(self):
        """Entry should not be expired within TTL."""
        entry = CacheEntry(
            result=[],
            timestamp=time.time()
        )
        
        assert entry.is_expired(ttl=60) is False
    
    def test_expired_after_ttl(self):
        """Entry should be expired after TTL."""
        entry = CacheEntry(
            result=[],
            timestamp=time.time() - 120  # 2 minutes ago
        )
        
        assert entry.is_expired(ttl=60) is True
