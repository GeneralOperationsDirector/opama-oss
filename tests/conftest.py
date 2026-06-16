"""
Pytest configuration and fixtures for test suite.

This file is automatically loaded by pytest.
"""

import os
import pytest
import requests
import time

# Override with API_BASE env var to target a different server.
# Default 8008 = local uvicorn; set API_BASE=http://localhost:6000 for Docker.
API_BASE = os.getenv("API_BASE", "http://localhost:8008")


@pytest.fixture(scope="session", autouse=True)
def check_api_running():
    """
    Verify API is running before tests start.
    This runs once at the beginning of the test session.
    """
    max_retries = 3
    retry_delay = 2

    for attempt in range(max_retries):
        try:
            response = requests.get(f"{API_BASE}/healthz", timeout=5)
            if response.status_code == 200:
                print(f"\n✅ API is running at {API_BASE}")
                return
        except requests.exceptions.RequestException:
            if attempt < max_retries - 1:
                print(f"\n⏳ API not ready, retrying in {retry_delay}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(retry_delay)
            else:
                pytest.exit(
                    f"\n❌ API not running at {API_BASE}\n"
                    f"Please start the backend first:\n"
                    f"  uvicorn app.main:app --reload --port 8008"
                )


@pytest.fixture
def api_base():
    """Provide API base URL to tests"""
    return API_BASE


@pytest.fixture
def test_user_id():
    """Provide test user ID"""
    return 1


@pytest.fixture
def auth_headers():
    """
    Bearer-token headers for endpoints that require a logged-in user.

    All user-data endpoints reject anonymous requests, so these tests need a
    real token for the target server. Set API_TOKEN to run them; they skip
    otherwise. For a local-auth instance, obtain one via POST /auth/login.
    """
    token = os.getenv("API_TOKEN", "")
    if not token:
        pytest.skip("Set API_TOKEN to run authenticated endpoint tests")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_card(api_base):
    """Get a sample card for testing"""
    response = requests.get(f"{api_base}/cards?limit=1", timeout=5)
    cards = response.json()
    if cards:
        return cards[0]
    pytest.skip("No cards available for testing")


@pytest.fixture
def sample_set(api_base):
    """Get a sample set for testing"""
    response = requests.get(f"{api_base}/cards/sets", timeout=5)
    sets = response.json()
    if sets:
        return sets[0]
    pytest.skip("No sets available for testing")


# Custom markers
def pytest_configure(config):
    """Register custom markers"""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
