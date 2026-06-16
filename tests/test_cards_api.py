"""
Test suite for Cards API endpoints.

Run with: pytest tests/test_cards_api.py -v
"""

import os
import pytest
import requests

API_BASE = os.getenv("API_BASE", "http://localhost:8008")
TIMEOUT = 5


class TestCardsEndpoints:
    """Test /cards endpoints"""

    def test_list_cards(self):
        """Test GET /cards returns card list"""
        response = requests.get(f"{API_BASE}/cards?limit=10", timeout=TIMEOUT)
        assert response.status_code == 200

        cards = response.json()
        assert isinstance(cards, list)
        assert len(cards) <= 10

        if cards:
            card = cards[0]
            assert "id" in card
            assert "name" in card
            assert "set_id" in card

    def test_list_cards_with_limit(self):
        """Test limit parameter works"""
        response = requests.get(f"{API_BASE}/cards?limit=5", timeout=TIMEOUT)
        assert response.status_code == 200

        cards = response.json()
        assert len(cards) <= 5

    def test_get_specific_card(self):
        """Test GET /cards/{card_id}"""
        # First get a card ID
        response = requests.get(f"{API_BASE}/cards?limit=1", timeout=TIMEOUT)
        cards = response.json()

        if cards:
            card_id = cards[0]["id"]

            # Now fetch that specific card
            response = requests.get(f"{API_BASE}/cards/{card_id}", timeout=TIMEOUT)
            assert response.status_code == 200

            card = response.json()
            assert card["id"] == card_id
            assert "name" in card

    def test_get_nonexistent_card(self):
        """Test GET /cards/{card_id} with invalid ID returns 404 or 422"""
        response = requests.get(
            f"{API_BASE}/cards/nonexistent-card-id-12345",
            timeout=TIMEOUT
        )
        # Can be 404 (not found) or 422 (validation error)
        assert response.status_code in [404, 422]

    def test_search_cards(self):
        """Test GET /cards/search with query"""
        response = requests.get(
            f"{API_BASE}/cards/search?q=pikachu&limit=5",
            timeout=TIMEOUT
        )
        assert response.status_code == 200

        data = response.json()

        # Handle both paginated and non-paginated responses
        if isinstance(data, dict) and "items" in data:
            # Paginated response
            results = data["items"]
            assert "total" in data
        else:
            # Simple list response
            results = data

        assert isinstance(results, list)

        # Results should contain "pikachu" in the name (case-insensitive)
        if results:
            for card in results[:5]:  # Check first 5
                assert "pikachu" in card["name"].lower()


class TestSetsEndpoints:
    """Test /cards/sets endpoints"""

    def test_list_sets(self):
        """Test GET /cards/sets returns set list"""
        response = requests.get(f"{API_BASE}/cards/sets", timeout=TIMEOUT)
        assert response.status_code == 200

        sets = response.json()
        assert isinstance(sets, list)
        if not sets:
            pytest.skip("Catalog not seeded — no sets to verify")

        # Check set structure
        if sets:
            set_obj = sets[0]
            assert "id" in set_obj
            assert "name" in set_obj
            assert "series" in set_obj

    def test_get_cards_by_set(self):
        """Test filtering cards by set_id"""
        # First get a set ID
        response = requests.get(f"{API_BASE}/cards/sets", timeout=TIMEOUT)
        sets = response.json()

        if sets:
            set_id = sets[0]["id"]

            # Get cards in that set
            response = requests.get(
                f"{API_BASE}/cards/search?set_id={set_id}&limit=10",
                timeout=TIMEOUT
            )
            assert response.status_code == 200

            data = response.json()

            # Handle both paginated and non-paginated responses
            if isinstance(data, dict) and "items" in data:
                cards = data["items"]
            else:
                cards = data

            # All cards should be from the requested set
            for card in cards:
                assert card["set_id"] == set_id


class TestCardDataIntegrity:
    """Test card data quality and consistency"""

    def test_card_has_required_fields(self):
        """Test cards have required fields"""
        response = requests.get(f"{API_BASE}/cards?limit=1", timeout=TIMEOUT)
        cards = response.json()

        if cards:
            card = cards[0]

            # Required fields
            assert card["id"] is not None
            assert card["name"] is not None
            assert card["set_id"] is not None

            # Common fields (may be None for some cards)
            assert "number" in card
            assert "rarity" in card
            assert "hp" in card
            assert "types" in card

    def test_database_has_cards(self):
        """Test database is not empty (skips on a freshly-initialized instance)"""
        response = requests.get(f"{API_BASE}/cards?limit=1", timeout=TIMEOUT)
        assert response.status_code == 200
        cards = response.json()

        if not cards:
            pytest.skip("Catalog not seeded — run scripts/import_cards.py to populate")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
