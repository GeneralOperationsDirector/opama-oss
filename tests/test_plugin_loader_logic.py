"""
Unit tests for plugin loader filtering logic.

Tests the resolve_enabled() semantics without importing FastAPI.
These run on the host with only PyYAML + stdlib.

Run with:
    pytest tests/test_plugin_loader_logic.py -v
"""

import pathlib
import pytest
import yaml
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Minimal replica of PluginManifest + resolve_enabled for offline testing
# ---------------------------------------------------------------------------
# We replicate the resolve_enabled() logic here rather than importing
# app.plugin_loader (which needs fastapi on the host).

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SERVICES_DIR = REPO_ROOT / "services"
# External plugins (e.g. marketplace) live outside services/ — loaded via
# PLUGIN_PATHS in production. See external_plugins/README.md / "repo split" prep.
EXTERNAL_PLUGINS_DIR = REPO_ROOT / "external_plugins"


@dataclass
class _Manifest:
    id: str
    tier: str = "core"


def _load_manifests() -> list[_Manifest]:
    manifests = []
    for plugins_dir in (SERVICES_DIR, EXTERNAL_PLUGINS_DIR):
        paths = sorted(plugins_dir.glob("*/plugin.yaml"))
        if plugins_dir == EXTERNAL_PLUGINS_DIR:
            # Multi-plugin packages (e.g. opama_pokemon_tcg) place their plugin.yaml
            # manifests one level deeper — mirrors discover_plugins().
            paths += sorted(plugins_dir.glob("*/*/plugin.yaml"))
        for path in paths:
            with open(path) as f:
                data = yaml.safe_load(f)
            manifests.append(_Manifest(id=data["id"], tier=data.get("tier", "core")))
    return manifests


def _resolve_enabled(all_plugins: list[_Manifest], raw_env: str) -> list[_Manifest]:
    """Replica of plugin_loader.resolve_enabled() for host-side tests."""
    raw = raw_env.strip()
    if not raw:
        return all_plugins
    enabled_ids = {s.strip() for s in raw.split(",") if s.strip()}
    return [p for p in all_plugins if p.id in enabled_ids]


@pytest.fixture(scope="module")
def all_plugins():
    return _load_manifests()


# ---------------------------------------------------------------------------
# resolve_enabled tests
# ---------------------------------------------------------------------------

class TestResolveEnabled:

    def test_empty_env_returns_all(self, all_plugins):
        """ENABLED_PLUGINS='' should return all plugins."""
        result = _resolve_enabled(all_plugins, "")
        assert len(result) == len(all_plugins)
        assert set(p.id for p in result) == set(p.id for p in all_plugins)

    def test_whitespace_only_env_returns_all(self, all_plugins):
        """ENABLED_PLUGINS='   ' should be treated as unset."""
        result = _resolve_enabled(all_plugins, "   ")
        assert len(result) == len(all_plugins)

    def test_single_plugin_filter(self, all_plugins):
        """ENABLED_PLUGINS='grading' should return only grading."""
        result = _resolve_enabled(all_plugins, "grading")
        assert len(result) == 1
        assert result[0].id == "grading"

    def test_multiple_plugin_filter(self, all_plugins):
        """ENABLED_PLUGINS='custom_assets,system,integrations' returns exactly those 3."""
        result = _resolve_enabled(all_plugins, "custom_assets,system,integrations")
        ids = {p.id for p in result}
        assert ids == {"custom_assets", "system", "integrations"}

    def test_order_preserved(self, all_plugins):
        """Returned plugins preserve the discovery order, not the ENABLED_PLUGINS order."""
        result = _resolve_enabled(all_plugins, "system,custom_assets")
        ids = [p.id for p in result]
        # custom_assets comes before system alphabetically (discovery is sorted)
        assert ids.index("custom_assets") < ids.index("system")

    def test_unknown_id_silently_excluded(self, all_plugins):
        """Unknown IDs in ENABLED_PLUGINS are silently ignored (not errors)."""
        result = _resolve_enabled(all_plugins, "grading,does_not_exist")
        assert len(result) == 1
        assert result[0].id == "grading"

    def test_spaces_around_commas_handled(self, all_plugins):
        """'grading , system' should parse both IDs correctly."""
        result = _resolve_enabled(all_plugins, "grading , system")
        ids = {p.id for p in result}
        assert ids == {"grading", "system"}

    def test_all_premium_subset(self, all_plugins):
        """Can enable exactly the 10 premium plugins."""
        premium_ids = {p.id for p in all_plugins if p.tier == "premium"}
        result = _resolve_enabled(all_plugins, ",".join(premium_ids))
        result_ids = {p.id for p in result}
        assert result_ids == premium_ids

    def test_all_core_subset(self, all_plugins):
        """Can enable exactly the core plugins."""
        core_ids = {p.id for p in all_plugins if p.tier == "core"}
        result = _resolve_enabled(all_plugins, ",".join(core_ids))
        result_ids = {p.id for p in result}
        assert result_ids == core_ids

    def test_duplicate_ids_in_env_not_duplicated(self, all_plugins):
        """'grading,grading' should not return grading twice."""
        result = _resolve_enabled(all_plugins, "grading,grading")
        grading_count = sum(1 for p in result if p.id == "grading")
        assert grading_count == 1

    def test_result_is_list(self, all_plugins):
        result = _resolve_enabled(all_plugins, "grading")
        assert isinstance(result, list)

    def test_empty_result_when_no_matches(self, all_plugins):
        """ENABLED_PLUGINS with no matching IDs returns empty list."""
        result = _resolve_enabled(all_plugins, "no_such_plugin,also_missing")
        assert result == []


# ---------------------------------------------------------------------------
# Plugin tier tests (read from manifests)
# ---------------------------------------------------------------------------

class TestPluginTiers:

    def test_five_core_plugins(self, all_plugins):
        """Expected exactly 5 core plugins: custom_assets, licensing, plugin_store, system, integrations."""
        core = {p.id for p in all_plugins if p.tier == "core"}
        assert core == {"custom_assets", "licensing", "plugin_store", "system", "integrations"}

    def test_eleven_premium_plugins(self, all_plugins):
        """Expected exactly 11 premium plugins (Phase 3 + Shopify scaffold)."""
        premium = [p for p in all_plugins if p.tier == "premium"]
        assert len(premium) == 11, f"Expected 11 premium plugins, got {len(premium)}: {[p.id for p in premium]}"

    def test_no_unknown_tiers(self, all_plugins):
        valid = {"core", "free", "premium", "enterprise"}
        bad = {p.id: p.tier for p in all_plugins if p.tier not in valid}
        assert not bad, f"Unknown tiers: {bad}"
