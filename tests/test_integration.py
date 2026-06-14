"""
Integration tests - test complete user workflows.

Run with: pytest tests/test_integration.py -v
"""

import os
import pytest
import requests
import time

API_BASE = os.getenv("API_BASE", "http://localhost:8008")
TIMEOUT = 10


class TestUserWorkflow:
    """Test complete user workflows end-to-end (authenticated — set API_TOKEN)"""

    def test_browse_and_add_to_inventory(self, auth_headers):
        """
        User story: Browse cards and add one to inventory

        Steps:
        1. List cards
        2. Pick a card
        3. Add to inventory
        4. Verify it's in inventory
        """
        # Step 1: Browse cards
        response = requests.get(f"{API_BASE}/cards?limit=10", timeout=TIMEOUT)
        assert response.status_code == 200
        cards = response.json()
        assert len(cards) > 0, "Should have cards to browse"

        # Step 2: Pick a card
        test_card = cards[0]
        card_id = test_card["id"]

        # Step 3: Add to inventory
        add_response = requests.post(
            f"{API_BASE}/inventory",
            json={
                "card_id": card_id,
                "quantity": 1,
                "condition": "NM"
            },
            headers=auth_headers,
            timeout=TIMEOUT
        )
        assert add_response.status_code in [200, 201]

        # Step 4: Verify in inventory
        inventory_response = requests.get(
            f"{API_BASE}/inventory/with_cards",
            headers=auth_headers,
            timeout=TIMEOUT
        )
        assert inventory_response.status_code == 200
        inventory = inventory_response.json()

        # Should find our card in inventory (with_cards returns nested structure)
        card_in_inventory = any(item["inventory"]["card_id"] == card_id for item in inventory)
        assert card_in_inventory, f"Card {card_id} should be in inventory"

    def test_build_deck_workflow(self, auth_headers):
        """
        User story: Create a deck and add cards

        Steps:
        1. Create a deck
        2. Find some cards
        3. Add cards to deck
        4. Verify deck has cards
        """
        # Step 1: Create deck
        deck_response = requests.post(
            f"{API_BASE}/decks",
            json={
                "name": f"Test Deck {int(time.time())}",
                "format": "standard",
                "strategy_notes": "Integration test deck"
            },
            headers=auth_headers,
            timeout=TIMEOUT
        )
        assert deck_response.status_code in [200, 201]
        deck = deck_response.json()
        deck_id = deck["id"]

        # Step 2: Find cards
        cards_response = requests.get(f"{API_BASE}/cards?limit=5", timeout=TIMEOUT)
        cards = cards_response.json()
        assert len(cards) >= 2, "Need at least 2 cards for test"

        # Step 3: Add multiple cards to deck
        for i, card in enumerate(cards[:3]):  # Add first 3 cards
            add_card_response = requests.post(
                f"{API_BASE}/decks/{deck_id}/cards",
                json={
                    "card_id": card["id"],
                    "quantity": 2
                },
                headers=auth_headers,
                timeout=TIMEOUT
            )
            assert add_card_response.status_code in [200, 201]

        # Step 4: Verify deck has cards
        deck_details = requests.get(
            f"{API_BASE}/decks/{deck_id}", headers=auth_headers, timeout=TIMEOUT
        )
        assert deck_details.status_code == 200

        deck_data = deck_details.json()
        assert "cards" in deck_data
        assert len(deck_data["cards"]) == 3, "Deck should have 3 cards"

    def test_search_and_filter_workflow(self):
        """
        User story: Search for specific cards

        Steps:
        1. Search by card name
        2. Filter by set
        3. Get card details
        """
        # Step 1: Search by name
        search_response = requests.get(
            f"{API_BASE}/cards/search?q=pikachu&limit=10",
            timeout=TIMEOUT
        )

        # If no Pikachu cards, try a different search
        if search_response.status_code == 200:
            data = search_response.json()
            # Search returns paginated response: {"total": X, "items": [...]}
            cards = data.get("items", data) if isinstance(data, dict) else data
            if cards:
                # Verify search results match query
                for card in cards:
                    assert "pikachu" in card["name"].lower()

        # Step 2: Filter by set
        sets_response = requests.get(f"{API_BASE}/cards/sets", timeout=TIMEOUT)
        assert sets_response.status_code == 200
        sets = sets_response.json()

        if sets:
            test_set_id = sets[0]["id"]

            set_cards_response = requests.get(
                f"{API_BASE}/cards/search?set_id={test_set_id}&limit=5",
                timeout=TIMEOUT
            )
            assert set_cards_response.status_code == 200
            set_cards_data = set_cards_response.json()
            # Extract items from paginated response
            set_cards = set_cards_data.get("items", set_cards_data) if isinstance(set_cards_data, dict) else set_cards_data

            # All cards should be from the specified set
            for card in set_cards:
                assert card["set_id"] == test_set_id

            # Step 3: Get details for one card
            if set_cards:
                card_id = set_cards[0]["id"]
                details_response = requests.get(
                    f"{API_BASE}/cards/{card_id}",
                    timeout=TIMEOUT
                )
                assert details_response.status_code == 200
                card_details = details_response.json()
                assert card_details["id"] == card_id


class TestDataConsistency:
    """Test data consistency across endpoints"""

    def test_inventory_card_references(self, auth_headers):
        """Test that inventory items reference valid cards"""
        inventory_response = requests.get(
            f"{API_BASE}/inventory",
            headers=auth_headers,
            timeout=TIMEOUT
        )

        if inventory_response.status_code != 200:
            pytest.skip("Could not fetch inventory")

        inventory = inventory_response.json()

        for item in inventory[:5]:  # Test first 5 items
            card_id = item["card_id"]

            # Verify card exists
            card_response = requests.get(
                f"{API_BASE}/cards/{card_id}",
                timeout=TIMEOUT
            )
            assert card_response.status_code == 200, \
                f"Inventory references non-existent card {card_id}"

    def test_deck_card_references(self, auth_headers):
        """Test that deck cards reference valid cards"""
        decks_response = requests.get(
            f"{API_BASE}/decks",
            headers=auth_headers,
            timeout=TIMEOUT
        )

        if decks_response.status_code != 200:
            pytest.skip("Could not fetch decks")

        decks = decks_response.json()

        if not decks:
            pytest.skip("No decks to test")

        # Test first deck
        deck_id = decks[0]["id"]
        deck_response = requests.get(
            f"{API_BASE}/decks/{deck_id}", headers=auth_headers, timeout=TIMEOUT
        )
        deck = deck_response.json()

        if "cards" in deck:
            for deck_card in deck["cards"][:5]:  # Test first 5 cards
                card_id = deck_card["card_id"]

                # Verify card exists
                card_response = requests.get(
                    f"{API_BASE}/cards/{card_id}",
                    timeout=TIMEOUT
                )
                assert card_response.status_code == 200, \
                    f"Deck references non-existent card {card_id}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
