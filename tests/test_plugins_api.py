"""
HTTP integration tests for the plugin system.

Tests the running Docker backend at localhost:6000.
Verifies that all plugins loaded correctly, the /plugins endpoint works,
and that every plugin's routes are still reachable after the Phase 1 refactor.

Run with:
    pytest tests/test_plugins_api.py -v

Requires the backend to be running:
    docker compose up -d
"""

import os
import pytest
import requests

API_BASE = os.getenv("API_BASE", "http://localhost:6000")
TIMEOUT = 5

EXPECTED_PLUGIN_IDS = {
    "ai", "catalog", "custom_assets", "decks", "grading",
    "integrations", "inventory", "licensing", "plugin_store",
    "portfolio", "showcase", "storefront", "system", "trading",
}

# Loaded from PLUGIN_PATHS when present (lives in its own repo) — optional.
OPTIONAL_PLUGIN_IDS = {"marketplace", "shopify"}

VALID_TIERS = {"core", "free", "premium", "enterprise"}


@pytest.fixture(scope="module")
def plugins_response():
    """Fetch /plugins once and share across all tests in this module."""
    r = requests.get(f"{API_BASE}/plugins", timeout=TIMEOUT)
    assert r.status_code == 200, f"/plugins returned {r.status_code}"
    return r.json()


@pytest.fixture(scope="module")
def plugins_by_id(plugins_response):
    return {p["id"]: p for p in plugins_response}


# ---------------------------------------------------------------------------
# /plugins endpoint
# ---------------------------------------------------------------------------

class TestPluginsEndpoint:

    def test_returns_200(self):
        r = requests.get(f"{API_BASE}/plugins", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_returns_json_list(self, plugins_response):
        assert isinstance(plugins_response, list)

    def test_returns_all_builtin_plugins(self, plugins_response):
        ids = {p["id"] for p in plugins_response}
        unexpected = ids - EXPECTED_PLUGIN_IDS - OPTIONAL_PLUGIN_IDS
        assert not unexpected, (
            f"Unexpected plugin IDs in /plugins response: {unexpected}"
        )

    def test_all_expected_ids_present(self, plugins_by_id):
        missing = EXPECTED_PLUGIN_IDS - set(plugins_by_id)
        assert not missing, f"Missing plugin IDs in /plugins response: {missing}"

    def test_each_plugin_has_required_fields(self, plugins_response):
        required = {"id", "name", "version", "tier", "description", "icon"}
        for plugin in plugins_response:
            missing = required - set(plugin)
            assert not missing, f"Plugin '{plugin.get('id')}' missing fields: {missing}"

    def test_all_tiers_valid(self, plugins_response):
        for plugin in plugins_response:
            assert plugin["tier"] in VALID_TIERS, \
                f"Plugin '{plugin['id']}' has invalid tier '{plugin['tier']}'"

    def test_core_plugins_present(self, plugins_by_id):
        for core_id in ("custom_assets", "licensing", "system", "integrations"):
            assert core_id in plugins_by_id, f"Core plugin '{core_id}' not loaded"
            assert plugins_by_id[core_id]["tier"] == "core"

    def test_premium_plugins_present(self, plugins_by_id):
        premium = {"ai", "catalog", "decks", "grading", "inventory",
                   "portfolio", "showcase", "storefront", "trading"}
        for pid in premium:
            assert pid in plugins_by_id, f"Premium plugin '{pid}' not loaded"
            assert plugins_by_id[pid]["tier"] == "premium"

    def test_marketplace_plugin_tier(self, plugins_by_id):
        """The external marketplace plugin is optional — verify its tier only when loaded."""
        if "marketplace" not in plugins_by_id:
            pytest.skip("marketplace external plugin not installed")
        assert plugins_by_id["marketplace"]["tier"] == "premium"

    def test_no_duplicate_ids(self, plugins_response):
        ids = [p["id"] for p in plugins_response]
        assert len(ids) == len(set(ids)), f"Duplicate plugin IDs in response: {ids}"


# ---------------------------------------------------------------------------
# Route smoke tests — one per plugin
# ---------------------------------------------------------------------------
# Each test hits the most basic route from a given plugin and verifies
# it's reachable (4xx is fine; 404 is not — that would mean the router
# didn't register).

class TestPluginRoutesSmokeTest:

    def _expect_not_404(self, url: str, method: str = "GET", **kwargs):
        r = requests.request(method, url, timeout=TIMEOUT, **kwargs)
        assert r.status_code != 404, f"{method} {url} returned 404 — plugin route not registered"
        return r

    def test_catalog_route_reachable(self):
        """GET /cards should return cards (plugin: catalog)."""
        r = requests.get(f"{API_BASE}/cards?limit=1", timeout=TIMEOUT)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_cards_sets_route_reachable(self):
        """GET /cards/sets should return sets (plugin: catalog)."""
        r = requests.get(f"{API_BASE}/cards/sets", timeout=TIMEOUT)
        assert r.status_code == 200

    def test_inventory_route_reachable(self):
        """GET /inventory requires auth, but must not 404 (plugin: inventory)."""
        self._expect_not_404(f"{API_BASE}/inventory")

    def test_decks_route_reachable(self):
        """GET /decks requires auth, but must not 404 (plugin: decks)."""
        self._expect_not_404(f"{API_BASE}/decks")

    def test_portfolio_route_reachable(self):
        """GET /portfolio/value requires auth, but must not 404 (plugin: portfolio)."""
        self._expect_not_404(f"{API_BASE}/portfolio/value")

    def test_showcase_route_reachable(self):
        """GET /showcases requires auth, but must not 404 (plugin: showcase)."""
        self._expect_not_404(f"{API_BASE}/showcases")

    def test_grading_history_route_reachable(self):
        """GET /grading/history requires auth, but must not 404 (plugin: grading)."""
        self._expect_not_404(f"{API_BASE}/grading/history")

    def test_storefront_settings_route_reachable(self):
        """GET /storefront/settings requires auth, but must not 404 (plugin: storefront)."""
        self._expect_not_404(f"{API_BASE}/storefront/settings")

    def test_ai_chat_route_reachable(self):
        """POST /ai/chat must not 404 (plugin: ai, combined router)."""
        # POST without body returns 422 (validation) — confirms route exists
        r = requests.post(f"{API_BASE}/ai/chat", timeout=TIMEOUT)
        assert r.status_code != 404, "POST /ai/chat returned 404 — AI chat route not registered"

    def test_suggest_route_reachable(self):
        """GET /suggest/{id} must be a registered route (plugin: ai, suggest sub-router).

        A 404 with FastAPI's generic {"detail": "Not Found"} body means the route
        isn't registered; a handler-raised 404 (e.g. "Deck not found" on an empty
        database) means the route exists and is fine.
        """
        r = requests.get(f"{API_BASE}/suggest/1", timeout=TIMEOUT)
        if r.status_code == 404:
            detail = r.json().get("detail", "")
            assert detail != "Not Found", \
                "GET /suggest/1 returned FastAPI's generic 404 — suggest route not registered"

    def test_marketplace_route_reachable(self, plugins_by_id):
        """GET /api/ebay/healthz must not 404 (optional external plugin: marketplace)."""
        if "marketplace" not in plugins_by_id:
            pytest.skip("marketplace external plugin not installed")
        r = requests.get(f"{API_BASE}/api/ebay/healthz", timeout=TIMEOUT)
        assert r.status_code != 404, "GET /api/ebay/healthz returned 404 — marketplace plugin not registered"

    def test_system_route_reachable(self):
        """GET /system/info requires auth, but must not 404 (plugin: system)."""
        self._expect_not_404(f"{API_BASE}/system/info")

    def test_custom_assets_route_reachable(self):
        """GET /assets requires auth, but must not 404 (plugin: custom_assets)."""
        self._expect_not_404(f"{API_BASE}/assets")

    def test_trading_wishlist_route_reachable(self):
        """GET /user/1/wishlist must not 404 (plugin: trading)."""
        self._expect_not_404(f"{API_BASE}/user/1/wishlist")

    def test_trading_tradelist_route_reachable(self):
        """GET /user/1/trade must not 404 (plugin: trading)."""
        self._expect_not_404(f"{API_BASE}/user/1/trade")

    def test_license_route_reachable(self):
        """GET /license must return 200 with license status (plugin: licensing)."""
        r = requests.get(f"{API_BASE}/license", timeout=TIMEOUT)
        assert r.status_code == 200, f"GET /license returned {r.status_code}"
        data = r.json()
        assert "valid" in data
        assert "tier" in data
        assert "modules" in data


# ---------------------------------------------------------------------------
# Auth is always loaded (not through plugin system)
# ---------------------------------------------------------------------------

class TestAuthAlwaysLoaded:

    def test_auth_me_returns_401_not_404(self):
        """GET /auth/me without token should be 401 (auth loaded) not 404 (missing)."""
        r = requests.get(f"{API_BASE}/auth/me", timeout=TIMEOUT)
        assert r.status_code == 401, \
            f"Expected 401 (unauthorized) from /auth/me, got {r.status_code}"

    def test_healthz_returns_ok(self):
        r = requests.get(f"{API_BASE}/healthz", timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json() == {"ok": True}


# ---------------------------------------------------------------------------
# OpenAPI schema reflects all plugin routes
# ---------------------------------------------------------------------------

class TestOpenAPISchema:

    @pytest.fixture(scope="class")
    def openapi(self):
        r = requests.get(f"{API_BASE}/openapi.json", timeout=TIMEOUT)
        assert r.status_code == 200
        return r.json()

    def test_schema_has_paths(self, openapi):
        assert "paths" in openapi
        assert len(openapi["paths"]) > 20, "OpenAPI schema should have many routes"

    def test_catalog_paths_in_schema(self, openapi):
        assert any(p.startswith("/cards") for p in openapi["paths"]), \
            "/cards paths missing from OpenAPI schema"

    def test_grading_paths_in_schema(self, openapi):
        assert any(p.startswith("/grading") for p in openapi["paths"]), \
            "/grading paths missing from OpenAPI schema"

    def test_ai_paths_in_schema(self, openapi):
        assert any(p.startswith("/ai") for p in openapi["paths"]), \
            "/ai paths missing from OpenAPI schema"

    def test_suggest_paths_in_schema(self, openapi):
        assert any(p.startswith("/suggest") for p in openapi["paths"]), \
            "/suggest paths missing from OpenAPI schema"

    def test_storefront_paths_in_schema(self, openapi):
        assert any(p.startswith("/storefront") for p in openapi["paths"]), \
            "/storefront paths missing from OpenAPI schema"

    def test_plugins_endpoint_in_schema(self, openapi):
        assert "/plugins" in openapi["paths"], \
            "/plugins endpoint missing from OpenAPI schema"

    def test_license_endpoint_in_schema(self, openapi):
        assert "/license" in openapi["paths"], \
            "/license endpoint missing from OpenAPI schema"
