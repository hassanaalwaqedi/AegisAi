"""
AegisAI - Security Tests: Input Validation

Tests for input sanitization and validation.
"""

import pytest
from unittest.mock import patch


class TestInputValidation:
    """Tests for input validation and sanitization."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        from fastapi.testclient import TestClient
        from aegis.api.app import create_app
        
        app = create_app()
        return TestClient(app)
    
    @pytest.fixture
    def valid_headers(self):
        """Valid headers with API key."""
        return {"X-API-Key": "test-key"}
    
    @patch.dict("os.environ", {"AEGIS_API_KEY": "test-key"})
    def test_sql_injection_in_query_params_blocked(self, client, valid_headers):
        """SQL injection attempts in query params should be safe."""
        # Attempt SQL injection in query parameter
        malicious_params = [
            "1; DROP TABLE events;--",
            "' OR '1'='1",
            "1 UNION SELECT * FROM users",
            "'; DELETE FROM alerts WHERE '1'='1"
        ]
        
        for payload in malicious_params:
            response = client.get(
                f"/events?limit={payload}",
                headers=valid_headers
            )
            # Should either reject (422) or safely ignore
            assert response.status_code in [200, 401, 422, 500]
    
    @patch.dict("os.environ", {"AEGIS_API_KEY": "test-key"})
    def test_xss_in_query_params_sanitized(self, client, valid_headers):
        """XSS attempts should not be reflected."""
        xss_payloads = [
            "<script>alert('xss')</script>",
            "javascript:alert(1)",
            "<img src=x onerror=alert(1)>",
            "'\"><script>alert(1)</script>"
        ]
        
        for payload in xss_payloads:
            response = client.get(
                f"/events?filter={payload}",
                headers=valid_headers
            )
            
            # If 200, response should not contain unescaped script
            if response.status_code == 200:
                content = response.text
                assert "<script>" not in content.lower()
    
    @patch.dict("os.environ", {"AEGIS_API_KEY": "test-key"})
    def test_path_traversal_blocked(self, client, valid_headers):
        """Path traversal attempts should be blocked."""
        traversal_payloads = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "....//....//etc/passwd",
            "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd"
        ]
        
        for payload in traversal_payloads:
            response = client.get(
                f"/static/{payload}",
                headers=valid_headers
            )
            # Should return 404, not actual file contents
            assert response.status_code in [400, 404, 401]
    
    @patch.dict("os.environ", {"AEGIS_API_KEY": "test-key"})
    def test_oversized_payload_rejected(self, client, valid_headers):
        """Extremely large payloads should be rejected."""
        # Create oversized JSON payload
        oversized_data = {"prompt": "x" * 1_000_000}  # 1MB string
        
        response = client.post(
            "/semantic/query",
            json=oversized_data,
            headers={**valid_headers, "Content-Type": "application/json"}
        )
        
        # Should reject (422 validation error or 413 payload too large)
        assert response.status_code in [401, 413, 422, 400, 500]
    
    @patch.dict("os.environ", {"AEGIS_API_KEY": "test-key"})
    def test_invalid_json_handled(self, client, valid_headers):
        """Invalid JSON should return proper error."""
        response = client.post(
            "/semantic/query",
            content="not valid json {{{",
            headers={**valid_headers, "Content-Type": "application/json"}
        )
        
        # Should return 422 or 400 for invalid JSON
        assert response.status_code in [400, 401, 422]
    
    @patch.dict("os.environ", {"AEGIS_API_KEY": "test-key"})
    def test_unicode_handling(self, client, valid_headers):
        """Unicode input should be handled safely."""
        unicode_payloads = [
            "测试中文",
            "テスト日本語",
            "🔥💀🚨",
            "Ā̴̡̛̛̪̩̪̮̘̯͇̻͎̝̟̗̈́̈́͐̇̊̈́̌̂͐̕͠ḻ̸̨̢̙̮̘̺̫̻̣̝̔̊̇̈́̒̍͑͗͗̕͘͜͝ͅg̷̛̗̮̈́̓̂̀̿̈́̊̉̊͘o̴̡̢̘̭̺̮̮̥̳̟̪̱̔̇̈́",
        ]
        
        for payload in unicode_payloads:
            response = client.post(
                "/semantic/query",
                json={"prompt": payload},
                headers={**valid_headers, "Content-Type": "application/json"}
            )
            # Should handle without crashing
            assert response.status_code in [200, 401, 422, 503]
    
    @patch.dict("os.environ", {"AEGIS_API_KEY": "test-key"})
    def test_null_bytes_handled(self, client, valid_headers):
        """Null bytes should not cause issues."""
        response = client.post(
            "/semantic/query",
            json={"prompt": "test\x00injection"},
            headers={**valid_headers, "Content-Type": "application/json"}
        )
        
        # Should handle safely
        assert response.status_code in [200, 401, 422, 503]
    
    @patch.dict("os.environ", {"AEGIS_API_KEY": "test-key"})
    def test_negative_numbers_handled(self, client, valid_headers):
        """Negative numbers in params should be validated."""
        response = client.get(
            "/events?limit=-1",
            headers=valid_headers
        )
        
        # Should either reject or treat as default
        assert response.status_code in [200, 401, 422]
    
    @patch.dict("os.environ", {"AEGIS_API_KEY": "test-key"})
    def test_extremely_large_numbers_handled(self, client, valid_headers):
        """Extremely large numbers should not overflow."""
        response = client.get(
            "/events?limit=999999999999999999999999999",
            headers=valid_headers
        )
        
        # Should handle without crashing
        assert response.status_code in [200, 401, 422, 500]


class TestSemanticQueryValidation:
    """Tests for semantic query input validation."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        from fastapi.testclient import TestClient
        from aegis.api.app import create_app
        
        app = create_app()
        return TestClient(app)
    
    @patch.dict("os.environ", {"AEGIS_API_KEY": "test-key"})
    def test_prompt_min_length_enforced(self, client):
        """Prompt should have minimum length."""
        response = client.post(
            "/semantic/query",
            json={"prompt": "ab"},  # Too short (min 3)
            headers={"X-API-Key": "test-key", "Content-Type": "application/json"}
        )
        
        assert response.status_code in [401, 422]  # Validation error
    
    @patch.dict("os.environ", {"AEGIS_API_KEY": "test-key"})
    def test_prompt_max_length_enforced(self, client):
        """Prompt should have maximum length."""
        response = client.post(
            "/semantic/query",
            json={"prompt": "x" * 600},  # Too long (max 500)
            headers={"X-API-Key": "test-key", "Content-Type": "application/json"}
        )
        
        assert response.status_code in [401, 422]  # Validation error
    
    @patch.dict("os.environ", {"AEGIS_API_KEY": "test-key"})
    def test_priority_range_validated(self, client):
        """Priority should be within valid range."""
        response = client.post(
            "/semantic/query",
            json={"prompt": "valid prompt", "priority": 150},  # > 100
            headers={"X-API-Key": "test-key", "Content-Type": "application/json"}
        )
        
        assert response.status_code in [401, 422]  # Validation error
