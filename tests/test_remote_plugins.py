"""
Unit tests for Phase 3 remote plugin support in app/plugin_loader.py.

Tests manifest parsing for remote plugins and the proxy router factory.
No FastAPI server needed — these are pure logic tests.

Run with:
    pytest tests/test_remote_plugins.py -v
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Manifest parsing
# ---------------------------------------------------------------------------

class TestRemoteManifestParsing:

    def _parse(self, data: dict):
        from app.plugin_loader import _manifest_from_dict
        return _manifest_from_dict(data)

    def test_local_type_is_default(self):
        m = self._parse({"id": "x", "name": "X", "router_module": "services.x.router"})
        assert m.type == "local"

    def test_remote_type_parsed(self):
        m = self._parse({
            "id": "vendor",
            "name": "Vendor Plugin",
            "type": "remote",
            "remote_url": "https://api.vendor.com/opama",
            "api_prefix": "/vendor",
        })
        assert m.type == "remote"
        assert m.remote_url == "https://api.vendor.com/opama"

    def test_auth_type_defaults_to_none(self):
        m = self._parse({"id": "x", "name": "X", "type": "remote", "remote_url": "https://x.com"})
        assert m.auth_type == "none"

    def test_auth_type_signed_jwt_parsed(self):
        m = self._parse({
            "id": "x", "name": "X", "type": "remote",
            "remote_url": "https://x.com", "auth_type": "signed_jwt",
        })
        assert m.auth_type == "signed_jwt"

    def test_scopes_parsed_as_list(self):
        m = self._parse({
            "id": "x", "name": "X", "type": "remote",
            "remote_url": "https://x.com",
            "scopes": ["inventory:read", "assets:read"],
        })
        assert m.scopes == ["inventory:read", "assets:read"]

    def test_scopes_default_empty(self):
        m = self._parse({"id": "x", "name": "X", "type": "remote", "remote_url": "https://x.com"})
        assert m.scopes == []

    def test_router_module_not_required_for_remote(self):
        m = self._parse({
            "id": "remote_plugin",
            "name": "Remote",
            "type": "remote",
            "remote_url": "https://api.example.com",
            "api_prefix": "/remote",
        })
        assert m.router_module == ""

    def test_local_manifest_still_works(self):
        m = self._parse({
            "id": "catalog",
            "name": "Catalog",
            "type": "local",
            "router_module": "services.catalog.router",
            "api_prefix": "/cards",
            "tier": "premium",
        })
        assert m.type == "local"
        assert m.router_module == "services.catalog.router"
        assert m.remote_url == ""

    def test_tags_parsed(self):
        m = self._parse({
            "id": "x", "name": "X", "type": "remote",
            "remote_url": "https://x.com",
            "tags": ["analytics", "reporting"],
        })
        assert m.tags == ["analytics", "reporting"]


# ---------------------------------------------------------------------------
# Proxy router factory — requires FastAPI (skipped on host, runs in Docker)
# ---------------------------------------------------------------------------

class TestRemoteProxyRouter:

    def test_returns_api_router(self):
        pytest.importorskip("fastapi")
        from fastapi import APIRouter
        from app.plugin_loader import _make_remote_proxy_router, PluginManifest
        m = PluginManifest(
            id="test_remote",
            name="Test Remote",
            type="remote",
            remote_url="https://api.example.com",
            auth_type="none",
        )
        router = _make_remote_proxy_router(m)
        assert isinstance(router, APIRouter)

    def test_router_has_catch_all_route(self):
        pytest.importorskip("fastapi")
        from app.plugin_loader import _make_remote_proxy_router, PluginManifest
        m = PluginManifest(
            id="test_remote",
            name="Test Remote",
            type="remote",
            remote_url="https://api.example.com",
        )
        router = _make_remote_proxy_router(m)
        paths = [str(r.path) for r in router.routes]
        assert any("{path:path}" in p for p in paths), \
            f"Expected a catch-all {{path:path}} route, got: {paths}"

    def test_router_supports_all_http_methods(self):
        pytest.importorskip("fastapi")
        from app.plugin_loader import _make_remote_proxy_router, PluginManifest
        m = PluginManifest(
            id="test_remote",
            name="Test Remote",
            type="remote",
            remote_url="https://api.example.com",
        )
        router = _make_remote_proxy_router(m)
        route = router.routes[0]
        expected_methods = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
        assert expected_methods.issubset(route.methods), \
            f"Missing methods: {expected_methods - route.methods}"

    def test_different_manifests_create_independent_routers(self):
        pytest.importorskip("fastapi")
        from app.plugin_loader import _make_remote_proxy_router, PluginManifest
        m1 = PluginManifest(id="plugin_a", name="A", type="remote", remote_url="https://a.com")
        m2 = PluginManifest(id="plugin_b", name="B", type="remote", remote_url="https://b.com")
        r1 = _make_remote_proxy_router(m1)
        r2 = _make_remote_proxy_router(m2)
        assert r1 is not r2


# ---------------------------------------------------------------------------
# load_plugins routing
# ---------------------------------------------------------------------------

class TestLoadPluginsDispatch:

    def test_local_plugin_imports_router_module(self, tmp_path, monkeypatch):
        """load_plugins() should import router_module for local plugins."""
        pytest.importorskip("fastapi")
        import sys
        from app.plugin_loader import PluginManifest, load_plugins, LoadedPlugin

        # Create a minimal fake router module in tmp_path
        pkg = tmp_path / "fake_service"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "router.py").write_text(
            "from fastapi import APIRouter\nrouter = APIRouter()\n"
        )
        monkeypatch.syspath_prepend(str(tmp_path))

        manifest = PluginManifest(
            id="fake",
            name="Fake",
            type="local",
            router_module="fake_service.router",
            tier="core",
        )
        results = load_plugins([manifest])
        assert len(results) == 1
        assert isinstance(results[0], LoadedPlugin)

        # Cleanup
        for k in list(sys.modules.keys()):
            if "fake_service" in k:
                del sys.modules[k]

    def test_remote_plugin_returns_proxy_router(self):
        pytest.importorskip("fastapi")
        from fastapi import APIRouter
        from app.plugin_loader import PluginManifest, load_plugins

        manifest = PluginManifest(
            id="remote_test",
            name="Remote Test",
            type="remote",
            remote_url="https://api.example.com",
            tier="free",
        )
        results = load_plugins([manifest])
        assert len(results) == 1
        assert isinstance(results[0].router, APIRouter)


# ---------------------------------------------------------------------------
# resolve_enabled still works with mixed local/remote
# ---------------------------------------------------------------------------

class TestResolveEnabledWithRemote:

    def test_remote_plugin_included_when_tier_matches(self, monkeypatch):
        monkeypatch.delenv("ENABLED_PLUGINS", raising=False)
        monkeypatch.delenv("OPAMA_LICENSE_KEY", raising=False)

        from app.plugin_loader import PluginManifest, resolve_enabled
        plugins = [
            PluginManifest(id="local_core", name="Core", type="local",
                           router_module="a.b", tier="core"),
            PluginManifest(id="remote_free", name="Remote Free", type="remote",
                           remote_url="https://x.com", tier="free"),
        ]
        enabled = resolve_enabled(plugins)
        ids = [p.id for p in enabled]
        assert "local_core" in ids
        assert "remote_free" in ids

    def test_remote_plugin_filtered_by_enabled_plugins_env(self, monkeypatch):
        monkeypatch.setenv("ENABLED_PLUGINS", "local_core")

        from app.plugin_loader import PluginManifest, resolve_enabled
        plugins = [
            PluginManifest(id="local_core", name="Core", type="local",
                           router_module="a.b", tier="core"),
            PluginManifest(id="remote_free", name="Remote", type="remote",
                           remote_url="https://x.com", tier="free"),
        ]
        enabled = resolve_enabled(plugins)
        assert [p.id for p in enabled] == ["local_core"]
