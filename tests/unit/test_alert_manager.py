"""
AegisAI - Alert Manager Unit Tests

Tests for alert generation, deduplication, and cooldown logic.

Sprint 1: Security & Testing Foundation
"""

import pytest
import time
from aegis.alerts import (
    AlertManager,
    AlertManagerConfig,
    AlertLevel,
    Alert
)


class TestAlertLevel:
    """Test AlertLevel enum."""
    
    def test_level_from_risk_level(self):
        """Risk levels should map to alert levels."""
        assert AlertLevel.from_risk_level("LOW") == AlertLevel.INFO
        assert AlertLevel.from_risk_level("MEDIUM") == AlertLevel.WARNING
        assert AlertLevel.from_risk_level("HIGH") == AlertLevel.HIGH
        assert AlertLevel.from_risk_level("CRITICAL") == AlertLevel.CRITICAL
    
    def test_level_priority(self):
        """Levels should have correct priority ordering."""
        assert AlertLevel.INFO.priority < AlertLevel.WARNING.priority
        assert AlertLevel.WARNING.priority < AlertLevel.HIGH.priority
        assert AlertLevel.HIGH.priority < AlertLevel.CRITICAL.priority


class TestAlert:
    """Test Alert dataclass."""
    
    def test_generate_id(self):
        """Generated IDs should be unique."""
        id1 = Alert.generate_id()
        id2 = Alert.generate_id()
        
        assert id1 != id2
        assert id1.startswith("evt_")
    
    def test_to_dict(self):
        """Alert should serialize to dictionary."""
        alert = Alert(
            event_id="evt_test_123",
            track_id=42,
            level=AlertLevel.HIGH,
            risk_score=0.75,
            message="Test alert"
        )
        
        data = alert.to_dict()
        
        assert data["event_id"] == "evt_test_123"
        assert data["track_id"] == 42
        assert data["risk_level"] == "HIGH"
        assert data["risk_score"] == 0.75
    
    def test_to_log_string(self):
        """Alert should format for logging."""
        alert = Alert(
            event_id="evt_test_123",
            track_id=42,
            level=AlertLevel.HIGH,
            risk_score=0.75,
            message="Test alert"
        )
        
        log_str = alert.to_log_string()
        
        assert "[HIGH]" in log_str
        assert "Track 42" in log_str


class TestAlertManager:
    """Test AlertManager logic."""
    
    def test_manager_creation(self, alert_manager):
        """Manager should be created successfully."""
        assert alert_manager is not None
        assert alert_manager.config.enabled
    
    def test_high_risk_generates_alert(self, alert_manager):
        """HIGH risk should generate an alert."""
        alert = alert_manager.process_risk(
            track_id=1,
            risk_level="HIGH",
            risk_score=0.55,
            message="Test high risk"
        )
        
        assert alert is not None
        assert alert.level == AlertLevel.HIGH
        assert alert.track_id == 1
    
    def test_low_risk_no_alert(self, alert_manager):
        """LOW risk should not generate alert (below min level)."""
        alert = alert_manager.process_risk(
            track_id=2,
            risk_level="LOW",
            risk_score=0.10,
            message="Test low risk"
        )
        
        assert alert is None
    
    def test_medium_risk_no_alert(self, alert_manager):
        """MEDIUM risk should not generate alert (below HIGH threshold)."""
        alert = alert_manager.process_risk(
            track_id=3,
            risk_level="MEDIUM",
            risk_score=0.35,
            message="Test medium risk"
        )
        
        assert alert is None
    
    def test_critical_generates_alert(self, alert_manager):
        """CRITICAL risk should generate an alert."""
        alert = alert_manager.process_risk(
            track_id=4,
            risk_level="CRITICAL",
            risk_score=0.85,
            message="Test critical risk"
        )
        
        assert alert is not None
        assert alert.level == AlertLevel.CRITICAL
    
    def test_cooldown_prevents_duplicate(self, alert_manager):
        """Cooldown should prevent duplicate alerts for same track."""
        # First alert should succeed
        alert1 = alert_manager.process_risk(
            track_id=10,
            risk_level="HIGH",
            risk_score=0.55,
            message="First alert"
        )
        
        # Immediate second alert should be suppressed
        alert2 = alert_manager.process_risk(
            track_id=10,
            risk_level="HIGH",
            risk_score=0.60,
            message="Second alert"
        )
        
        assert alert1 is not None
        assert alert2 is None  # Suppressed by cooldown
    
    def test_cooldown_expires(self, alert_manager):
        """Alert should be allowed after cooldown expires."""
        # First alert
        alert1 = alert_manager.process_risk(
            track_id=20,
            risk_level="HIGH",
            risk_score=0.55,
            message="First alert"
        )
        
        # Wait for cooldown (config is 1 second for testing)
        time.sleep(1.2)
        
        # Second alert should succeed
        alert2 = alert_manager.process_risk(
            track_id=20,
            risk_level="HIGH",
            risk_score=0.60,
            message="After cooldown"
        )
        
        assert alert1 is not None
        assert alert2 is not None
    
    def test_different_tracks_no_cooldown(self, alert_manager):
        """Different tracks should not share cooldown."""
        alert1 = alert_manager.process_risk(
            track_id=30,
            risk_level="HIGH",
            risk_score=0.55,
            message="Track 30"
        )
        
        alert2 = alert_manager.process_risk(
            track_id=31,
            risk_level="HIGH",
            risk_score=0.60,
            message="Track 31"
        )
        
        assert alert1 is not None
        assert alert2 is not None
    
    def test_alert_count_tracking(self, alert_manager):
        """Manager should track total alerts."""
        initial_count = alert_manager.alert_count
        
        alert_manager.process_risk(
            track_id=40,
            risk_level="HIGH",
            risk_score=0.55,
            message="Counted alert"
        )
        
        assert alert_manager.alert_count == initial_count + 1
    
    def test_get_summary(self, alert_manager):
        """Should return valid summary statistics."""
        summary = alert_manager.get_summary()
        
        assert summary is not None
        assert "HIGH" in summary.by_level
        assert "CRITICAL" in summary.by_level
    
    def test_disabled_manager_no_alerts(self):
        """Disabled manager should not generate alerts."""
        config = AlertManagerConfig(enabled=False)
        manager = AlertManager(config=config)
        
        alert = manager.process_risk(
            track_id=50,
            risk_level="CRITICAL",
            risk_score=0.90,
            message="Should not alert"
        )
        
        assert alert is None
