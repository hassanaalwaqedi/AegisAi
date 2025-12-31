"""
AegisAI - API Integration Tests

Tests for REST API endpoints with authentication.

Sprint 1: Security & Testing Foundation
"""

import pytest
from fastapi.testclient import TestClient
from aegis.api.app import create_app


class TestAPIAuthentication:
    """Test API authentication requirements."""
    
    def test_status_without_key_rejected(self, api_client):
        """Request without API key should be rejected."""
        response = api_client.get("/status")
        
        # Should be 401 Unauthorized
        assert response.status_code == 401
    
    def test_status_with_valid_key(self, api_client, api_headers):
        """Request with valid API key should succeed."""
        response = api_client.get("/status", headers=api_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
    
    def test_status_with_invalid_key(self, api_client):
        """Request with invalid API key should be rejected."""
        headers = {"X-API-Key": "wrong-key"}
        response = api_client.get("/status", headers=headers)
        
        assert response.status_code == 401
    
    def test_events_requires_auth(self, api_client):
        """Events endpoint should require authentication."""
        response = api_client.get("/events")
        
        assert response.status_code == 401
    
    def test_tracks_requires_auth(self, api_client):
        """Tracks endpoint should require authentication."""
        response = api_client.get("/tracks")
        
        assert response.status_code == 401
    
    def test_statistics_requires_auth(self, api_client):
        """Statistics endpoint should require authentication."""
        response = api_client.get("/statistics")
        
        assert response.status_code == 401


class TestStatusEndpoint:
    """Test /status endpoint."""
    
    def test_status_response_structure(self, api_client, api_headers):
        """Status response should have correct structure."""
        response = api_client.get("/status", headers=api_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert "status" in data
        assert "system" in data
    
    def test_status_health_check(self, api_client, api_headers):
        """Health check should return healthy."""
        response = api_client.get("/status/health", headers=api_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestEventsEndpoint:
    """Test /events endpoint."""
    
    def test_events_response_structure(self, api_client, api_headers):
        """Events response should have correct structure."""
        response = api_client.get("/events", headers=api_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert "count" in data
        assert "events" in data
        assert isinstance(data["events"], list)
    
    def test_events_limit_parameter(self, api_client, api_headers):
        """Events should accept limit parameter."""
        response = api_client.get("/events?limit=5", headers=api_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "count" in data


class TestTracksEndpoint:
    """Test /tracks endpoint."""
    
    def test_tracks_response_structure(self, api_client, api_headers):
        """Tracks response should have correct structure."""
        response = api_client.get("/tracks", headers=api_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert "count" in data
        assert "tracks" in data
        assert isinstance(data["tracks"], list)
    
    def test_concerning_tracks(self, api_client, api_headers):
        """Concerning tracks endpoint should work."""
        response = api_client.get("/tracks/concerning", headers=api_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "count" in data


class TestStatisticsEndpoint:
    """Test /statistics endpoint."""
    
    def test_statistics_response_structure(self, api_client, api_headers):
        """Statistics response should have correct structure."""
        response = api_client.get("/statistics", headers=api_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert "crowd" in data
        assert "risk" in data
        assert "processing" in data


class TestRootEndpoint:
    """Test root endpoint."""
    
    def test_root_returns_info(self, api_client, api_headers):
        """Root should return API information."""
        response = api_client.get("/", headers=api_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert "name" in data
        assert data["name"] == "AegisAI API"
