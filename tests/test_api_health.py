"""
Test suite for API health and basic connectivity.

Run with: pytest tests/test_api_health.py -v
"""

import os
import pytest
import requests
import time

# Configuration
API_BASE = os.getenv("API_BASE", "http://localhost:8008")
TIMEOUT = 5


class TestAPIHealth:
    """Test basic API health and availability"""

    def test_health_endpoint(self):
        """Test /healthz endpoint returns 200"""
        response = requests.get(f"{API_BASE}/healthz", timeout=TIMEOUT)
        assert response.status_code == 200, "Health check should return 200"

        # Response should be JSON
        data = response.json()
        assert isinstance(data, dict), "Health check should return JSON object"

    def test_api_docs_available(self):
        """Test OpenAPI docs are accessible"""
        response = requests.get(f"{API_BASE}/docs", timeout=TIMEOUT)
        assert response.status_code == 200, "API docs should be available"
        assert "text/html" in response.headers.get("content-type", "")

    def test_openapi_json(self):
        """Test OpenAPI schema is available"""
        response = requests.get(f"{API_BASE}/openapi.json", timeout=TIMEOUT)
        assert response.status_code == 200
        schema = response.json()
        assert "openapi" in schema
        assert "paths" in schema

    def test_cors_headers(self):
        """Test CORS headers are present"""
        response = requests.options(
            f"{API_BASE}/cards",
            headers={"Origin": "http://localhost:5173"},
            timeout=TIMEOUT
        )
        # CORS headers should be present
        assert "access-control-allow-origin" in response.headers


class TestAPIPerformance:
    """Test API response times"""

    def test_health_check_performance(self):
        """Health check should respond quickly"""
        start = time.time()
        response = requests.get(f"{API_BASE}/healthz", timeout=TIMEOUT)
        duration = time.time() - start

        assert response.status_code == 200
        assert duration < 1.0, f"Health check took {duration}s, should be under 1s"

    def test_cards_list_performance(self):
        """Card listing should respond in reasonable time"""
        start = time.time()
        response = requests.get(f"{API_BASE}/cards?limit=10", timeout=TIMEOUT)
        duration = time.time() - start

        assert response.status_code == 200
        assert duration < 2.0, f"Cards list took {duration}s, should be under 2s"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
