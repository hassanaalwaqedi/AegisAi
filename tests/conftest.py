"""
AegisAI - Test Configuration and Fixtures

Provides pytest fixtures for unit and integration testing.

Sprint 1: Security & Testing Foundation
"""

import os
import sys
import pytest
from unittest.mock import MagicMock

# Set test environment
os.environ["AEGIS_DEBUG"] = "true"
os.environ["AEGIS_API_KEY"] = "test-api-key-12345"


# ═══════════════════════════════════════════════════════════
# MOCK FIXTURES
# ═══════════════════════════════════════════════════════════

@pytest.fixture
def sample_track():
    """Create a sample track object for testing."""
    class MockTrack:
        track_id = 1
        class_id = 0
        class_name = "Person"
        bbox = (100, 100, 200, 200)
        confidence = 0.95
    return MockTrack()


@pytest.fixture
def sample_tracks():
    """Create multiple sample tracks."""
    tracks = []
    for i in range(5):
        class MockTrack:
            track_id = i + 1
            class_id = 0
            class_name = "Person"
            bbox = (100 + i*50, 100, 200 + i*50, 200)
            confidence = 0.9 + i*0.01
        tracks.append(MockTrack())
    return tracks


# ═══════════════════════════════════════════════════════════
# ANALYSIS FIXTURES
# ═══════════════════════════════════════════════════════════

@pytest.fixture
def motion_state():
    """Create a sample motion state."""
    from aegis.analysis import MotionState
    return MotionState(
        speed=5.0,
        smoothed_speed=4.5,
        velocity=(3.0, 4.0),
        direction=0.927,  # ~53 degrees
        acceleration=0.5,
        is_stationary=False
    )


@pytest.fixture
def behavior_flags():
    """Create sample behavior flags."""
    from aegis.analysis import BehaviorFlags, BehaviorType
    return BehaviorFlags(
        is_stationary=False,
        is_loitering=True,
        is_running=False,
        sudden_speed_change=False,
        direction_reversal=False,
        is_erratic=False,
        stationary_duration=10.0,
        direction_variance=0.2
    )


@pytest.fixture
def crowd_metrics():
    """Create sample crowd metrics."""
    from aegis.analysis import CrowdMetrics
    return CrowdMetrics(
        person_count=10,
        vehicle_count=2,
        grid_densities={},
        max_density=5,
        crowd_detected=False
    )


@pytest.fixture
def track_analysis(motion_state, behavior_flags):
    """Create a sample track analysis."""
    from aegis.analysis import TrackAnalysis
    return TrackAnalysis(
        track_id=1,
        class_id=0,
        class_name="Person",
        motion=motion_state,
        behavior=behavior_flags,
        history_length=60,
        time_tracked=5.0,
        current_position=(150.0, 150.0),
        current_bbox=(100, 100, 200, 200)
    )


# ═══════════════════════════════════════════════════════════
# RISK FIXTURES
# ═══════════════════════════════════════════════════════════

@pytest.fixture
def risk_weights():
    """Create risk weights for testing."""
    from aegis.risk import RiskWeights
    return RiskWeights(
        loitering=0.25,
        speed_anomaly=0.18,
        direction_change=0.15,
        crowd_density=0.12,
        zone_context=0.15,
        erratic_motion=0.10
    )


@pytest.fixture
def risk_thresholds():
    """Create risk thresholds for testing."""
    from aegis.risk import RiskThresholds
    return RiskThresholds(
        medium=0.25,
        high=0.50,
        critical=0.75
    )


@pytest.fixture
def risk_engine_config(risk_weights, risk_thresholds):
    """Create a risk engine config for testing."""
    from aegis.risk import RiskEngineConfig, TemporalConfig
    return RiskEngineConfig(
        weights=risk_weights,
        thresholds=risk_thresholds,
        temporal=TemporalConfig(),
        use_zones=False,
        use_temporal=False
    )


@pytest.fixture
def risk_engine(risk_engine_config):
    """Create a risk engine for testing."""
    from aegis.risk import RiskEngine
    return RiskEngine(config=risk_engine_config)


# ═══════════════════════════════════════════════════════════
# ALERT FIXTURES
# ═══════════════════════════════════════════════════════════

@pytest.fixture
def alert_manager_config():
    """Create alert manager config for testing."""
    from aegis.alerts import AlertManagerConfig, AlertLevel
    return AlertManagerConfig(
        enabled=True,
        min_level=AlertLevel.HIGH,
        cooldown_seconds=1.0,  # Short for testing
        log_to_file=False
    )


@pytest.fixture
def alert_manager(alert_manager_config):
    """Create an alert manager for testing."""
    from aegis.alerts import AlertManager
    return AlertManager(config=alert_manager_config)


# ═══════════════════════════════════════════════════════════
# API FIXTURES
# ═══════════════════════════════════════════════════════════

@pytest.fixture
def api_client():
    """Create a test client for the API."""
    from fastapi.testclient import TestClient
    from aegis.api.app import create_app
    
    app = create_app()
    return TestClient(app)


@pytest.fixture
def api_headers():
    """Get headers with valid API key."""
    return {"X-API-Key": "test-api-key-12345"}
