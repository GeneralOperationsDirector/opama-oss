"""
Test suite for Inventory API endpoints.

All /inventory endpoints require auth. Set API_TOKEN to a valid bearer token
for the target server to run the authenticated tests; they skip otherwise.

Run with: pytest tests/test_inventory_api.py -v
"""

import os
import pytest
import requests

API_BASE = os.getenv("API_BASE", "http://localhost:8008")
TIMEOUT = 5


class TestInventoryAuth:
    """Anonymous requests must be rejected"""

    def test_get_inventory_requires_auth(self):
        response = requests.get(f"{API_BASE}/inventory", timeout=TIMEOUT)
        assert response.status_code in [401, 403]

    def test_add_inventory_requires_auth(self):
        response = requests.post(
            f"{API_BASE}/inventory",
            json={"card_id": "anything", "quantity": 1},
            timeout=TIMEOUT,
        )
        assert response.status_code in [401, 403]


class TestInventoryEndpoints:
    """Test /inventory endpoints (authenticated)"""

    def test_get_user_inventory(self, auth_headers):
        """Test GET /inventory"""
        response = requests.get(
            f"{API_BASE}/inventory", headers=auth_headers, timeout=TIMEOUT
        )
        assert response.status_code == 200

        inventory = response.json()
        assert isinstance(inventory, list)

        # Check inventory item structure if any exist
        if inventory:
            item = inventory[0]
            assert "id" in item
            assert "user_id" in item
            assert "card_id" in item
            assert "quantity" in item

    def test_get_inventory_with_cards(self, auth_headers):
        """Test GET /inventory/with_cards"""
        response = requests.get(
            f"{API_BASE}/inventory/with_cards", headers=auth_headers, timeout=TIMEOUT
        )
        assert response.status_code == 200

        inventory = response.json()
        assert isinstance(inventory, list)

        # Items should have nested structure with inventory and card
        if inventory:
            item = inventory[0]
            assert "inventory" in item
            assert "card" in item
            assert "card_id" in item["inventory"]
            assert "quantity" in item["inventory"]
            # Card details should be populated
            assert item["card"]["id"] == item["inventory"]["card_id"]

    def test_add_inventory_item(self, auth_headers):
        """Test POST /inventory to add an item"""
        # First get a card to add
        cards_response = requests.get(f"{API_BASE}/cards?limit=1", timeout=TIMEOUT)
        cards = cards_response.json()

        if not cards:
            pytest.skip("No cards available to test with")

        card_id = cards[0]["id"]

        payload = {
            "card_id": card_id,
            "quantity": 1,
            "condition": "NM",
        }

        response = requests.post(
            f"{API_BASE}/inventory", json=payload, headers=auth_headers, timeout=TIMEOUT
        )

        # Should be 200 (created) or might merge with existing
        assert response.status_code in [200, 201]

        result = response.json()
        assert "id" in result
        assert "merged" in result
        # Note: API returns {"id": ..., "merged": true}, not full item

    def test_inventory_export_csv(self, auth_headers):
        """Test GET /inventory/export.csv"""
        response = requests.get(
            f"{API_BASE}/inventory/export.csv", headers=auth_headers, timeout=TIMEOUT
        )
        assert response.status_code == 200

        # Should be CSV format
        assert "text/csv" in response.headers.get("content-type", "")

        # Should have CSV headers
        csv_content = response.text
        assert "card_id" in csv_content.lower() or "name" in csv_content.lower()


class TestInventoryValidation:
    """Test inventory validation and error handling (authenticated)"""

    def test_add_inventory_invalid_card(self, auth_headers):
        """Test adding inventory with invalid card_id"""
        payload = {
            "card_id": "nonexistent-card-12345",
            "quantity": 1,
        }

        response = requests.post(
            f"{API_BASE}/inventory", json=payload, headers=auth_headers, timeout=TIMEOUT
        )

        # Should return error (404 or 400)
        assert response.status_code in [400, 404]

    def test_add_inventory_missing_fields(self, auth_headers):
        """Test adding inventory without required fields"""
        response = requests.post(
            f"{API_BASE}/inventory", json={}, headers=auth_headers, timeout=TIMEOUT
        )

        # Should return validation error
        assert response.status_code == 422  # FastAPI validation error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
