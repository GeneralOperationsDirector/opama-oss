"""
Unit tests for plugin.yaml manifests.

Validates that every service plugin manifest is structurally correct.
These tests run on the host with only PyYAML (no fastapi needed).

Run with:
    pytest tests/test_plugin_manifests.py -v
"""

import pathlib
import pytest
import yaml

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SERVICES_DIR = REPO_ROOT / "services"
# External plugins (code outside services/, loaded via PLUGIN_PATHS in production —
# see external_plugins/README.md and the "repo split" prep work). Hardcoded here
# rather than read from PLUGIN_PATHS so manifest validation doesn't depend on env.
EXTERNAL_PLUGINS_DIR = REPO_ROOT / "external_plugins"

# Out of scope: marketplace-installed type=local dynamic plugins (downloaded at
# runtime into DYNAMIC_PLUGINS_ROOT, not part of the repo tree) are covered by
# tests/test_dynamic_local_install.py instead.

VALID_TIERS = {"core", "free", "premium", "enterprise"}
VALID_NAV_POSITIONS = {"topnav", "dashboard-only", "hidden"}

# IDs we expect to exist after Phase 3
EXPECTED_PLUGIN_IDS = {
    "ai", "catalog", "custom_assets", "decks", "grading",
    "integrations", "inventory", "licensing", "marketplace", "plugin_store",
    "portfolio", "shopify", "showcase", "storefront", "system", "trading",
}

# Core plugins must always be present regardless of ENABLED_PLUGINS
CORE_PLUGIN_IDS = {"custom_assets", "licensing", "plugin_store", "system", "integrations"}

# Premium plugins that must exist (but can be gated by ENABLED_PLUGINS)
PREMIUM_PLUGIN_IDS = {
    "ai", "catalog", "decks", "grading", "inventory",
    "marketplace", "portfolio", "shopify", "showcase", "storefront", "trading",
}


def load_all_manifests() -> list[dict]:
    """Load every plugin.yaml in services/*/ and external_plugins/*/ (or */*/ for
    multi-plugin packages like opama_pokemon_tcg — mirrors discover_plugins())."""
    manifests = []
    for plugins_dir in (SERVICES_DIR, EXTERNAL_PLUGINS_DIR):
        paths = sorted(plugins_dir.glob("*/plugin.yaml"))
        if plugins_dir == EXTERNAL_PLUGINS_DIR:
            paths += sorted(plugins_dir.glob("*/*/plugin.yaml"))
        for path in paths:
            with open(path) as f:
                data = yaml.safe_load(f)
            data["_path"] = str(path)   # attach source path for error messages
            manifests.append(data)
    return manifests


@pytest.fixture(scope="module")
def all_manifests():
    return load_all_manifests()


@pytest.fixture(scope="module")
def manifest_by_id(all_manifests):
    return {m["id"]: m for m in all_manifests}


# ---------------------------------------------------------------------------
# Discovery tests
# ---------------------------------------------------------------------------

class TestManifestDiscovery:

    def test_manifest_count(self, all_manifests):
        """Exactly 16 plugin.yaml files should exist after Phase 3 + Shopify scaffold."""
        assert len(all_manifests) == 16, (
            f"Expected 16 manifests, found {len(all_manifests)}: "
            f"{[m['id'] for m in all_manifests]}"
        )

    def test_all_expected_ids_present(self, manifest_by_id):
        """Every expected plugin ID must have a manifest."""
        missing = EXPECTED_PLUGIN_IDS - set(manifest_by_id)
        assert not missing, f"Missing plugin manifests for: {missing}"

    def test_no_extra_unexpected_ids(self, manifest_by_id):
        """No unexpected plugin IDs should exist."""
        extra = set(manifest_by_id) - EXPECTED_PLUGIN_IDS
        assert not extra, f"Unexpected plugin IDs found: {extra}"


# ---------------------------------------------------------------------------
# Required fields
# ---------------------------------------------------------------------------

class TestRequiredFields:

    @pytest.mark.parametrize("field", ["id", "name", "tier", "version"])
    def test_required_field_present_in_all(self, all_manifests, field):
        """Every manifest must have this field."""
        missing = [m["_path"] for m in all_manifests if field not in m]
        assert not missing, f"Field '{field}' missing in: {missing}"

    def test_local_plugins_have_router_module(self, all_manifests):
        """Local plugins (type=local or type absent) must declare router_module."""
        bad = [
            m["_path"] for m in all_manifests
            if m.get("type", "local") == "local" and not m.get("router_module")
        ]
        assert not bad, f"Local plugins missing router_module: {bad}"

    def test_remote_plugins_have_remote_url(self, all_manifests):
        """Remote plugins must declare remote_url."""
        bad = [
            m["_path"] for m in all_manifests
            if m.get("type") == "remote" and not m.get("remote_url")
        ]
        assert not bad, f"Remote plugins missing remote_url: {bad}"

    def test_no_duplicate_ids(self, all_manifests):
        """Each plugin must have a unique id."""
        ids = [m["id"] for m in all_manifests]
        seen, dupes = set(), set()
        for i in ids:
            if i in seen:
                dupes.add(i)
            seen.add(i)
        assert not dupes, f"Duplicate plugin IDs: {dupes}"

    def test_ids_are_strings(self, all_manifests):
        for m in all_manifests:
            assert isinstance(m["id"], str) and m["id"].strip(), \
                f"id must be non-empty string in {m['_path']}"

    def test_names_are_strings(self, all_manifests):
        for m in all_manifests:
            assert isinstance(m["name"], str) and m["name"].strip(), \
                f"name must be non-empty string in {m['_path']}"

    def test_router_module_looks_like_python_path(self, all_manifests):
        """Local plugin router_module must look like a dotted Python module path."""
        for m in all_manifests:
            if m.get("type", "local") != "local":
                continue
            rm = m.get("router_module", "")
            assert isinstance(rm, str) and "." in rm and not rm.startswith("."), \
                f"router_module '{rm}' doesn't look like an absolute Python path in {m['_path']}"

    def test_router_module_uses_known_convention(self, all_manifests):
        """Local plugin routers live under services/ (in-repo) or follow the
        opama_<id> external-package convention (PLUGIN_PATHS — see
        external_plugins/README.md and the "repo split" prep work)."""
        for m in all_manifests:
            if m.get("type", "local") != "local":
                continue
            rm = m.get("router_module", "")
            assert rm.startswith("services.") or rm.startswith("opama_"), (
                f"router_module '{rm}' should start with 'services.' (in-repo) "
                f"or 'opama_' (external plugin package) in {m['_path']}"
            )


# ---------------------------------------------------------------------------
# External plugin convention (PLUGIN_PATHS — "repo split" prep)
#
# Proves the discovery+import mechanism opama_loader relies on actually holds
# on disk: a manifest that declares router_module="opama_marketplace.router"
# must live in a directory that is itself an importable package
# (external_plugins/opama_marketplace/{__init__.py, router.py, plugin.yaml}),
# so that adding external_plugins/ to sys.path makes the dotted path resolve —
# exactly what app.plugin_loader.discover_plugins()/_ensure_on_syspath() do.
# This runs offline (no fastapi import — see module docstring).
# ---------------------------------------------------------------------------

class TestExternalPluginConvention:

    def test_external_manifests_are_discovered(self, manifest_by_id):
        """The external_plugins/ directory is scanned alongside services/."""
        assert "marketplace" in manifest_by_id
        assert EXTERNAL_PLUGINS_DIR.is_dir(), (
            f"{EXTERNAL_PLUGINS_DIR} should exist — it's the PLUGIN_PATHS reference root"
        )

    def test_external_router_modules_resolve_to_real_packages(self, all_manifests):
        """Every opama_<id> router_module maps to an importable package directory
        directly under external_plugins/ — proving sys.path injection of that
        single directory is sufficient for importlib.import_module() to resolve it."""
        external = [
            m for m in all_manifests
            if m.get("type", "local") == "local" and m.get("router_module", "").startswith("opama_")
        ]
        assert external, "expected at least one external-package plugin (opama_marketplace) for this prep work to be provable"

        for m in external:
            rm = m["router_module"]
            package_name, _, module_path = rm.partition(".")
            package_dir = EXTERNAL_PLUGINS_DIR / package_name
            assert package_dir.is_dir(), \
                f"router_module '{rm}' implies a package dir at {package_dir}, but it doesn't exist"
            assert (package_dir / "__init__.py").exists(), \
                f"{package_dir} must be a real package (missing __init__.py)"
            # The manifest's own plugin.yaml must live under package_dir — either
            # directly (single-plugin packages, e.g. opama_marketplace/plugin.yaml)
            # or one level deeper (multi-plugin packages, e.g.
            # opama_pokemon_tcg/catalog/plugin.yaml) — proving it's reachable once
            # external_plugins/ is added to sys.path.
            manifest_path = pathlib.Path(m["_path"])
            assert package_dir in manifest_path.parents, \
                f"{manifest_path} must live under {package_dir} (mirrors services/<id>/plugin.yaml)"
            module_file = package_dir.parent / pathlib.Path(*rm.split(".")).with_suffix(".py")
            assert module_file.exists(), \
                f"router_module '{rm}' implies {module_file}, but it doesn't exist"

    def test_external_plugin_has_pyproject(self, all_manifests):
        """External plugins ship a pyproject.toml — the shape they'd need as a
        standalone repo (see external_plugins/README.md for what's still open
        before an actual repo extraction)."""
        for m in all_manifests:
            rm = m.get("router_module", "")
            if not rm.startswith("opama_"):
                continue
            package_name = rm.split(".", 1)[0]
            assert (EXTERNAL_PLUGINS_DIR / package_name / "pyproject.toml").exists(), \
                f"external plugin '{package_name}' should declare a pyproject.toml"


# ---------------------------------------------------------------------------
# Tier validation
# ---------------------------------------------------------------------------

class TestTierValues:

    def test_all_tiers_valid(self, all_manifests):
        for m in all_manifests:
            assert m["tier"] in VALID_TIERS, \
                f"Invalid tier '{m['tier']}' in {m['_path']}"

    def test_core_plugins_have_core_tier(self, manifest_by_id):
        for plugin_id in CORE_PLUGIN_IDS:
            if plugin_id in manifest_by_id:
                assert manifest_by_id[plugin_id]["tier"] == "core", \
                    f"Plugin '{plugin_id}' should have tier 'core'"

    def test_premium_plugins_have_premium_tier(self, manifest_by_id):
        for plugin_id in PREMIUM_PLUGIN_IDS:
            if plugin_id in manifest_by_id:
                assert manifest_by_id[plugin_id]["tier"] == "premium", \
                    f"Plugin '{plugin_id}' should have tier 'premium'"


# ---------------------------------------------------------------------------
# Optional fields with type checks
# ---------------------------------------------------------------------------

class TestOptionalFields:

    def test_tags_is_list_when_present(self, all_manifests):
        for m in all_manifests:
            if "tags" in m:
                assert isinstance(m["tags"], list), \
                    f"'tags' must be a list in {m['_path']}"

    def test_model_modules_is_list_when_present(self, all_manifests):
        for m in all_manifests:
            if "model_modules" in m:
                assert isinstance(m["model_modules"], list), \
                    f"'model_modules' must be a list in {m['_path']}"

    def test_requires_is_list_when_present(self, all_manifests):
        for m in all_manifests:
            if "requires" in m:
                assert isinstance(m["requires"], list), \
                    f"'requires' must be a list in {m['_path']}"

    def test_api_prefix_format(self, all_manifests):
        """api_prefix must be either empty string or start with '/'."""
        for m in all_manifests:
            prefix = m.get("api_prefix", "")
            assert prefix == "" or prefix.startswith("/"), \
                f"api_prefix '{prefix}' must be '' or start with '/' in {m['_path']}"

    def test_version_semver_like(self, all_manifests):
        """Version should look like x.y.z."""
        for m in all_manifests:
            v = m.get("version", "")
            parts = str(v).split(".")
            assert len(parts) == 3 and all(p.isdigit() for p in parts), \
                f"version '{v}' should be x.y.z format in {m['_path']}"

    def test_icon_is_string_when_present(self, all_manifests):
        for m in all_manifests:
            if "icon" in m and m["icon"] is not None:
                assert isinstance(m["icon"], str), \
                    f"'icon' must be a string in {m['_path']}"


# ---------------------------------------------------------------------------
# Cross-reference: requires must reference valid IDs
# ---------------------------------------------------------------------------

class TestDependencyGraph:

    def test_requires_references_valid_ids(self, all_manifests):
        """Every entry in 'requires' must be a valid plugin ID or 'auth'."""
        known_ids = {m["id"] for m in all_manifests} | {"auth"}
        for m in all_manifests:
            for dep in m.get("requires", []):
                assert dep in known_ids, \
                    f"Plugin '{m['id']}' requires unknown id '{dep}' in {m['_path']}"

    def test_no_self_dependency(self, all_manifests):
        """A plugin must not require itself."""
        for m in all_manifests:
            assert m["id"] not in m.get("requires", []), \
                f"Plugin '{m['id']}' requires itself in {m['_path']}"

    def test_valid_plugin_type(self, all_manifests):
        """Plugin type must be 'local' or 'remote'."""
        valid = {"local", "remote"}
        for m in all_manifests:
            t = m.get("type", "local")
            assert t in valid, f"Invalid type '{t}' in {m['_path']}"

    def test_valid_auth_type_when_present(self, all_manifests):
        """auth_type (when present) must be 'none' or 'signed_jwt'."""
        valid = {"none", "signed_jwt"}
        for m in all_manifests:
            if "auth_type" in m:
                assert m["auth_type"] in valid, \
                    f"Invalid auth_type '{m['auth_type']}' in {m['_path']}"

    def test_auth_is_in_requires_for_non_core(self, manifest_by_id):
        """Every plugin with protected endpoints should require 'auth' (directly or transitively).

        Exception: 'licensing' exposes a public /license endpoint by design.
        """
        AUTH_EXEMPT = {"licensing"}
        for plugin_id, m in manifest_by_id.items():
            if plugin_id in AUTH_EXEMPT:
                continue
            requires = m.get("requires", [])
            assert "auth" in requires or any(
                "auth" in manifest_by_id.get(dep, {}).get("requires", [])
                for dep in requires
            ), f"Plugin '{plugin_id}' has no path to 'auth' in its requires chain"


# ---------------------------------------------------------------------------
# Known cross-plugin data dependencies (FK / FK-like references) — regression
# guard. These relationships live in models.py, not plugin.yaml, so they
# can't be derived generically from the manifests alone. If a manifest's
# `requires` ever drops one of these, a plugin can be enabled without the
# plugin that owns the table its rows point into — discover_plugins() and
# load_plugin_models() would still succeed (they register every table
# regardless of ENABLED_PLUGINS), but the dependent plugin's routes would
# reference rows in a table whose owning router/sync logic isn't mounted.
# See external_plugins/opama_pokemon_tcg/README.md "Module dependencies" and
# external_plugins/opama_shopify/README.md "Dependencies" for the narrative.
# ---------------------------------------------------------------------------

KNOWN_DATA_DEPENDENCIES = {
    # opama_pokemon_tcg: inventory.InventoryItem.card_id, decks.DeckCard.card_id,
    # and trading.{WishList,TradeItem}.card_id all reference catalog.Card.
    "inventory": {"catalog"},
    "decks": {"catalog"},
    "trading": {"catalog"},
    # opama_shopify: ShopifyProductMapping.catalog_id refers to an
    # opama_storefront catalog entry id.
    "shopify": {"storefront"},
    # opama_grading: CardGradeResult.asset_id has a real DB foreign key to
    # customasset.id (card_id/inventory_item_id are deliberately soft
    # references and don't count here).
    "grading": {"custom_assets"},
}


class TestKnownDataDependencies:

    def test_data_dependencies_declared_in_requires(self, manifest_by_id):
        """A plugin with a known FK/data dependency on another plugin's table
        must declare that plugin in `requires` (directly)."""
        for plugin_id, deps in KNOWN_DATA_DEPENDENCIES.items():
            if plugin_id not in manifest_by_id:
                continue
            requires = set(manifest_by_id[plugin_id].get("requires", []))
            missing = deps - requires
            assert not missing, (
                f"Plugin '{plugin_id}' has a data dependency on {missing} "
                f"(see {manifest_by_id[plugin_id]['_path']}) but doesn't "
                f"declare it in `requires`"
            )


# ---------------------------------------------------------------------------
# Specific plugin spot-checks
# ---------------------------------------------------------------------------

class TestSpecificPlugins:

    def test_ai_plugin_uses_combined_router(self, manifest_by_id):
        """AI plugin should use the combined opama_ai.router (not suggest_router or chat_router)."""
        ai = manifest_by_id["ai"]
        assert ai["router_module"] == "opama_ai.router", \
            "AI plugin should use combined router, not suggest_router or chat_router"

    def test_catalog_has_correct_prefix(self, manifest_by_id):
        assert manifest_by_id["catalog"]["api_prefix"] == "/cards"

    def test_inventory_has_correct_prefix(self, manifest_by_id):
        assert manifest_by_id["inventory"]["api_prefix"] == "/inventory"

    def test_decks_has_correct_prefix(self, manifest_by_id):
        assert manifest_by_id["decks"]["api_prefix"] == "/decks"

    def test_portfolio_has_correct_prefix(self, manifest_by_id):
        assert manifest_by_id["portfolio"]["api_prefix"] == "/portfolio"

    def test_showcase_has_correct_prefix(self, manifest_by_id):
        assert manifest_by_id["showcase"]["api_prefix"] == "/showcases"

    def test_grading_declares_model_module(self, manifest_by_id):
        """Grading has its own models.py so it must declare it."""
        assert "opama_grading.models" in manifest_by_id["grading"].get("model_modules", [])

    def test_storefront_declares_model_module(self, manifest_by_id):
        assert "opama_storefront.models" in manifest_by_id["storefront"].get("model_modules", [])

    def test_custom_assets_declares_model_module(self, manifest_by_id):
        assert "services.custom_assets.models" in manifest_by_id["custom_assets"].get("model_modules", [])

    def test_plugin_store_is_core(self, manifest_by_id):
        assert manifest_by_id["plugin_store"]["tier"] == "core"

    def test_plugin_store_has_empty_api_prefix(self, manifest_by_id):
        assert manifest_by_id["plugin_store"].get("api_prefix", "") == ""

    def test_plugin_store_declares_model_module(self, manifest_by_id):
        assert "services.plugin_store.models" in manifest_by_id["plugin_store"].get("model_modules", [])
