"""
Test suite for Decks API endpoints.

All /decks endpoints require auth. Set API_TOKEN to a valid bearer token for
the target server to run the authenticated tests; they skip otherwise.

Run with: pytest tests/test_decks_api.py -v
"""

import os
import pytest
import requests

API_BASE = os.getenv("API_BASE", "http://localhost:8008")
TIMEOUT = 5


class TestDecksAuth:
    """Anonymous requests must be rejected"""

    def test_list_decks_requires_auth(self):
        response = requests.get(f"{API_BASE}/decks", timeout=TIMEOUT)
        assert response.status_code in [401, 403]

    def test_create_deck_requires_auth(self):
        response = requests.post(
            f"{API_BASE}/decks", json={"name": "x"}, timeout=TIMEOUT
        )
        assert response.status_code in [401, 403]


class TestDecksEndpoints:
    """Test /decks endpoints (authenticated)"""

    def test_list_user_decks(self, auth_headers):
        """Test GET /decks"""
        response = requests.get(
            f"{API_BASE}/decks", headers=auth_headers, timeout=TIMEOUT
        )
        assert response.status_code == 200

        decks = response.json()
        assert isinstance(decks, list)

        # Check deck structure
        if decks:
            deck = decks[0]
            assert "id" in deck
            assert "name" in deck
            assert "user_id" in deck

    def test_create_deck(self, auth_headers):
        """Test POST /decks to create a new deck"""
        payload = {
            "name": "Test Deck - Automated",
            "format": "standard",
            "strategy_notes": "Created by automated test",
        }

        response = requests.post(
            f"{API_BASE}/decks", json=payload, headers=auth_headers, timeout=TIMEOUT
        )

        assert response.status_code in [200, 201]

        deck = response.json()
        assert deck["name"] == payload["name"]
        assert "id" in deck

    def test_get_deck_details(self, auth_headers):
        """Test GET /decks/{deck_id}"""
        # First create a deck
        create_response = requests.post(
            f"{API_BASE}/decks",
            json={"name": "Test Deck for Details", "format": "standard"},
            headers=auth_headers,
            timeout=TIMEOUT,
        )

        if create_response.status_code not in [200, 201]:
            pytest.skip("Could not create test deck")

        deck_id = create_response.json()["id"]

        # Get deck details
        response = requests.get(
            f"{API_BASE}/decks/{deck_id}", headers=auth_headers, timeout=TIMEOUT
        )
        assert response.status_code == 200

        data = response.json()
        assert "deck" in data
        assert "cards" in data
        assert data["deck"]["id"] == deck_id

    def test_add_card_to_deck(self, auth_headers):
        """Test POST /decks/{deck_id}/cards"""
        # Create a deck
        deck_response = requests.post(
            f"{API_BASE}/decks",
            json={"name": "Test Deck for Cards", "format": "standard"},
            headers=auth_headers,
            timeout=TIMEOUT,
        )

        if deck_response.status_code not in [200, 201]:
            pytest.skip("Could not create test deck")

        deck_id = deck_response.json()["id"]

        # Get a card to add
        cards_response = requests.get(f"{API_BASE}/cards?limit=1", timeout=TIMEOUT)
        cards = cards_response.json()

        if not cards:
            pytest.skip("No cards available")

        card_id = cards[0]["id"]

        # Add card to deck
        payload = {"card_id": card_id, "quantity": 2}

        response = requests.post(
            f"{API_BASE}/decks/{deck_id}/cards",
            json=payload,
            headers=auth_headers,
            timeout=TIMEOUT,
        )

        assert response.status_code in [200, 201]

        result = response.json()
        assert result["card_id"] == card_id
        assert result["quantity"] == 2


class TestDecksValidation:
    """Test deck validation and constraints (authenticated)"""

    def test_create_deck_missing_name(self, auth_headers):
        """Test creating deck without name"""
        response = requests.post(
            f"{API_BASE}/decks",
            json={"format": "standard"},  # missing name
            headers=auth_headers,
            timeout=TIMEOUT,
        )

        # Should return validation error
        assert response.status_code in [400, 422]

    def test_get_nonexistent_deck(self, auth_headers):
        """Test getting a deck that doesn't exist"""
        response = requests.get(
            f"{API_BASE}/decks/999999", headers=auth_headers, timeout=TIMEOUT
        )
        assert response.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
