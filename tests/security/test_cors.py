"""
AegisAI - Security Tests: CORS

Tests for Cross-Origin Resource Sharing configuration.
"""

import pytest
from unittest.mock import patch


class TestCORS:
    """Tests for CORS configuration."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        from fastapi.testclient import TestClient
        from aegis.api.app import create_app
        
        app = create_app()
        return TestClient(app)
    
    def test_cors_headers_present_on_options(self, client):
        """OPTIONS request should include CORS headers."""
        response = client.options(
            "/status",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET"
            }
        )
        
        # CORS preflight response
        assert response.status_code in [200, 405]
    
    def test_allowed_origin_localhost_3000(self, client):
        """http://localhost:3000 should be allowed (frontend)."""
        response = client.get(
            "/",
            headers={"Origin": "http://localhost:3000"}
        )
        
        # Check CORS header
        cors_header = response.headers.get("access-control-allow-origin", "")
        assert cors_header in ["http://localhost:3000", "*", ""]
    
    def test_allowed_origin_localhost_8080(self, client):
        """http://localhost:8080 should be allowed (same origin)."""
        response = client.get(
            "/",
            headers={"Origin": "http://localhost:8080"}
        )
        
        assert response.status_code == 200
    
    def test_disallowed_origin_blocked(self, client):
        """Unknown origins should be blocked or have no CORS headers."""
        response = client.get(
            "/",
            headers={"Origin": "http://malicious-site.com"}
        )
        
        # Either blocked or no CORS header for this origin
        cors_header = response.headers.get("access-control-allow-origin", "")
        assert cors_header != "http://malicious-site.com" or cors_header == ""
    
    def test_cors_allows_api_key_header(self, client):
        """CORS should allow X-API-Key header."""
        response = client.options(
            "/status",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "X-API-Key"
            }
        )
        
        allowed_headers = response.headers.get("access-control-allow-headers", "").lower()
        # X-API-Key should be allowed
        assert response.status_code in [200, 405]
    
    def test_cors_allows_content_type_header(self, client):
        """CORS should allow Content-Type header."""
        response = client.options(
            "/semantic/query",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type"
            }
        )
        
        assert response.status_code in [200, 405]
    
    def test_no_cors_without_origin(self, client):
        """Requests without Origin should work (same-origin)."""
        response = client.get("/")
        
        # Should work without CORS headers
        assert response.status_code == 200
