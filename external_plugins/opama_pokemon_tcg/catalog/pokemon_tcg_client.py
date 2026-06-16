"""
Pokemon TCG API Client

A robust client for interacting with the Pokemon TCG API (https://pokemontcg.io/v2).
Handles authentication, retries, rate limiting, and pagination.

This client consolidates logic from:
- scripts/export_all_series.py (set listing, retry logic)
- scripts/fetch_cards_for_set.py (card fetching with pagination)

Usage:
    from opama_pokemon_tcg.catalog.pokemon_tcg_client import PokemonTCGClient

    client = PokemonTCGClient(api_key="your_key")  # API key optional
    sets = client.list_all_sets()
    cards = client.fetch_set_cards("me1")
"""

import os
import time
from typing import Dict, List, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class PokemonTCGClient:
    """
    Client for Pokemon TCG API with retry logic and rate limiting.

    Features:
    - Automatic retry on failures (exponential backoff)
    - Rate limiting (configurable delay between requests)
    - Session pooling for connection reuse
    - Pagination handling
    """

    BASE_URL = "https://api.pokemontcg.io/v2"

    # Fields to request from the API (reduces payload size)
    CARD_FIELDS = [
        "id", "name", "set.id", "set.name", "set.series", "number", "rarity",
        "supertype", "subtypes", "types", "hp", "evolvesFrom", "regulationMark",
        "artist", "abilities", "attacks", "weaknesses", "resistances",
        "retreatCost", "rules", "flavorText", "legalities.standard",
        "legalities.expanded", "legalities.unlimited", "nationalPokedexNumbers",
        "releaseDate", "tcgplayer.productId", "images.small", "images.large"
    ]

    def __init__(
        self,
        api_key: Optional[str] = None,
        rate_limit_delay: float = 1.0,
        timeout: int = 60,
        max_retries: int = 5
    ):
        """
        Initialize the Pokemon TCG API client.

        Args:
            api_key: Optional API key from pokemontcg.io
            rate_limit_delay: Seconds to wait between requests (default: 1.0)
            timeout: Request timeout in seconds (default: 60)
            max_retries: Max retry attempts on failures (default: 5)
        """
        self.api_key = api_key or os.getenv("POKEMON_TCG_API_KEY")
        self.rate_limit_delay = rate_limit_delay
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = self._create_session()
        self._last_request_time = 0.0

    def _create_session(self) -> requests.Session:
        """
        Create a requests session with retry logic.

        Retries on:
        - 429 (Too Many Requests)
        - 500, 502, 503, 504 (Server errors)
        """
        session = requests.Session()

        # Configure exponential backoff retry strategy
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=0.8,  # 0.8s, 1.6s, 3.2s, 6.4s, 12.8s
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
            raise_on_status=False,
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        # Set headers
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
        }
        if self.api_key:
            headers["X-Api-Key"] = self.api_key

        session.headers.update(headers)

        return session

    def _rate_limit(self):
        """
        Enforce rate limiting between requests.

        Ensures at least rate_limit_delay seconds between API calls.
        """
        if self.rate_limit_delay > 0:
            elapsed = time.time() - self._last_request_time
            if elapsed < self.rate_limit_delay:
                time.sleep(self.rate_limit_delay - elapsed)

        self._last_request_time = time.time()

    def _request(
        self,
        endpoint: str,
        params: Optional[Dict] = None
    ) -> Dict:
        """
        Make a request to the Pokemon TCG API with error handling.

        Args:
            endpoint: API endpoint (e.g., "/sets", "/cards")
            params: Query parameters

        Returns:
            JSON response as dict

        Raises:
            requests.HTTPError: On non-2xx status codes after retries
            requests.Timeout: On timeout
            requests.RequestException: On other request errors
        """
        self._rate_limit()

        url = f"{self.BASE_URL}{endpoint}"
        response = self.session.get(url, params=params or {}, timeout=self.timeout)

        # Raise for status codes (will trigger retries via adapter)
        response.raise_for_status()

        return response.json()

    def list_all_sets(self) -> List[Dict]:
        """
        Fetch all Pokemon TCG sets from the API.

        Handles pagination automatically.

        Returns:
            List of set dictionaries with fields:
            - id (str): Set ID (e.g., "me1", "sv10")
            - name (str): Set name (e.g., "Mega Evolution")
            - series (str): Series name (e.g., "Scarlet & Violet")
            - releaseDate (str): ISO date (e.g., "2025-09-26")
            - total (int): Number of cards in set
            - printedTotal (int): Printed total (excluding secrets)

        Example:
            >>> client = PokemonTCGClient()
            >>> sets = client.list_all_sets()
            >>> len(sets)
            169
            >>> sets[0]['name']
            'Phantasmal Flames'
        """
        all_sets = []
        page = 1
        page_size = 250  # API max

        while True:
            params = {
                "page": page,
                "pageSize": page_size,
                "orderBy": "-releaseDate"  # Newest first
            }

            response = self._request("/sets", params)
            data = response.get("data", [])

            if not data:
                break

            all_sets.extend(data)

            # Stop if we got fewer results than page size (last page)
            if len(data) < page_size:
                break

            page += 1

        return all_sets

    def fetch_set_cards(
        self,
        set_id: str,
        page_size: int = 100
    ) -> List[Dict]:
        """
        Fetch all cards for a specific set.

        Handles pagination automatically.

        Args:
            set_id: Pokemon TCG set ID (e.g., "me1", "sv10")
            page_size: Cards per page (default: 100, max: 250)

        Returns:
            List of card dictionaries with all card data

        Example:
            >>> client = PokemonTCGClient()
            >>> cards = client.fetch_set_cards("me1")
            >>> len(cards)
            132
            >>> cards[0]['name']
            'Venusaur ex'
        """
        all_cards = []
        page = 1

        while True:
            params = {
                "q": f"set.id:{set_id}",
                "page": page,
                "pageSize": min(page_size, 250),  # API max is 250
                "select": ",".join(self.CARD_FIELDS),
            }

            response = self._request("/cards", params)
            data = response.get("data", [])

            if not data:
                break

            all_cards.extend(data)

            # Stop if we got fewer results than requested (last page)
            if len(data) < page_size:
                break

            page += 1

        return all_cards

    def get_set_info(self, set_id: str) -> Optional[Dict]:
        """
        Get information about a specific set.

        Args:
            set_id: Pokemon TCG set ID (e.g., "me1")

        Returns:
            Set dictionary with detailed info, or None if not found

        Example:
            >>> client = PokemonTCGClient()
            >>> set_info = client.get_set_info("me1")
            >>> set_info['name']
            'Mega Evolution'
            >>> set_info['total']
            132
        """
        try:
            response = self._request(f"/sets/{set_id}")
            return response.get("data")
        except requests.HTTPError as e:
            if e.response and e.response.status_code == 404:
                return None
            raise

    def search_cards(
        self,
        query: str,
        page_size: int = 100,
        max_results: Optional[int] = None
    ) -> List[Dict]:
        """
        Search for cards using Pokemon TCG API query syntax.

        Args:
            query: Search query (e.g., "name:Pikachu rarity:Rare")
            page_size: Results per page (default: 100)
            max_results: Maximum total results to return (default: unlimited)

        Returns:
            List of matching card dictionaries

        Query Examples:
            - "name:Charizard"
            - "types:fire supertype:Pokemon"
            - "set.id:sv10 rarity:\"Illustration Rare\""

        Example:
            >>> client = PokemonTCGClient()
            >>> cards = client.search_cards("name:Pikachu", max_results=10)
            >>> len(cards)
            10
        """
        all_cards = []
        page = 1

        while True:
            params = {
                "q": query,
                "page": page,
                "pageSize": min(page_size, 250),
                "select": ",".join(self.CARD_FIELDS),
            }

            response = self._request("/cards", params)
            data = response.get("data", [])

            if not data:
                break

            all_cards.extend(data)

            # Check max_results limit
            if max_results and len(all_cards) >= max_results:
                return all_cards[:max_results]

            # Check if last page
            if len(data) < page_size:
                break

            page += 1

        return all_cards
