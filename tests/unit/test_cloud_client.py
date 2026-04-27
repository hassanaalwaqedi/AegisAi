"""
AegisAI - Cloud Client Unit Tests

Tests the cloud communication layer including circuit breaker,
event queuing, and verdict handling.
"""

import time
import pytest
from unittest.mock import patch, MagicMock

from aegis.cloud.cloud_client import CloudClient, CircuitBreaker
from aegis.cloud.cloud_types import CloudVerdict
from aegis.edge.event_types import SuspiciousEvent
from config import CloudConfig


# ── Tests: CircuitBreaker ──

class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker(failure_threshold=3)
        assert cb.state == "CLOSED"
        assert cb.is_open is False
    
    def test_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "CLOSED"
        cb.record_failure()
        assert cb.state == "OPEN"
        assert cb.is_open is True
    
    def test_resets_on_success(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.state == "CLOSED"
        cb.record_failure()
        assert cb.state == "CLOSED"  # Counter reset
    
    def test_half_open_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=2, reset_timeout=0.1)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "OPEN"
        
        time.sleep(0.15)
        assert cb.state == "HALF_OPEN"


# ── Tests: CloudClient ──

class TestCloudClient:
    def test_disabled_by_default(self):
        client = CloudClient(cloud_config=CloudConfig())
        assert client.is_enabled is False
    
    def test_enabled_with_url(self):
        config = CloudConfig(
            enabled=True,
            api_url="http://localhost:8000",
            api_key="test-key",
        )
        client = CloudClient(cloud_config=config)
        assert client.is_enabled is True
    
    def test_enqueue_when_disabled(self):
        client = CloudClient(cloud_config=CloudConfig())
        event = SuspiciousEvent(event_id="test")
        assert client.enqueue_event(event) is False
    
    def test_enqueue_when_enabled(self):
        config = CloudConfig(
            enabled=True,
            api_url="http://localhost:8000",
        )
        client = CloudClient(cloud_config=config)
        event = SuspiciousEvent(event_id="test")
        assert client.enqueue_event(event) is True
        assert client.queue_size == 1
    
    def test_enqueue_when_circuit_open(self):
        config = CloudConfig(
            enabled=True,
            api_url="http://localhost:8000",
            circuit_breaker_failures=1,
        )
        client = CloudClient(cloud_config=config)
        
        # Force circuit open
        client._circuit.record_failure()
        
        event = SuspiciousEvent(event_id="test")
        assert client.enqueue_event(event) is False
    
    def test_stats(self):
        config = CloudConfig(enabled=True, api_url="http://localhost:8000")
        client = CloudClient(cloud_config=config)
        stats = client.get_stats()
        
        assert stats["enabled"] is True
        assert stats["running"] is False
        assert stats["events_sent"] == 0
        assert stats["circuit_state"] == "CLOSED"


# ── Tests: CloudVerdict ──

class TestCloudVerdict:
    def test_to_dict(self):
        v = CloudVerdict(
            event_id="test-123",
            enhanced_risk_score=0.85,
            risk_level="HIGH",
            weapon_type="gun",
            holding_confidence=0.92,
            explanation="Armed person detected",
            models_used=["clip", "sam"],
        )
        d = v.to_dict()
        assert d["event_id"] == "test-123"
        assert d["enhanced_risk_score"] == 0.85
        assert d["weapon_type"] == "gun"
    
    def test_from_dict(self):
        data = {
            "event_id": "test-456",
            "enhanced_risk_score": 0.6,
            "risk_level": "MEDIUM",
            "explanation": "Suspicious activity",
        }
        v = CloudVerdict.from_dict(data)
        assert v.event_id == "test-456"
        assert v.risk_level == "MEDIUM"
    
    def test_is_threat(self):
        high = CloudVerdict(risk_level="HIGH")
        low = CloudVerdict(risk_level="LOW")
        assert high.is_threat is True
        assert low.is_threat is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
