"""
Integration-style tests for load_dynamic_plugins() — type=local dynamic
plugin loading, corrupted-install resilience, and the GC sweep.

Complements test_plugin_installer.py (the download/extract pipeline) by
testing the loader half: given a DynamicPlugin row pointing at an
already-extracted package on disk, does load_dynamic_plugins()...
  - import its router and build a usable LoadedPlugin?
  - skip a broken/missing install gracefully without crashing startup?
  - sweep DYNAMIC_PLUGINS_ROOT for orphaned directories afterward (the same
    mechanism that finalizes uninstalls and post-update cleanup)?

Out of scope here (covered elsewhere):
  - SSRF guard on download_url, archive safe-extraction, model_modules=[]
    validation, mint_download_token — all unit-tested directly against
    app/plugin_installer.py in test_plugin_installer.py.
  - License-gating and the admin-only HTTP install/uninstall endpoints in
    services/plugin_store/router.py — would need a live authenticated
    session; uninstall's hard-delete-then-GC behavior is exercised here
    indirectly via TestGcSweepAfterLoad (a row disappearing from the DB is
    exactly what makes its install dir "orphaned").

Run with:
    pytest tests/test_dynamic_local_install.py -v
"""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlmodel")
pytest.importorskip("yaml")


def _local_row(**overrides):
    """SimpleNamespace mimicking a type=local DynamicPlugin row (see services/plugin_store/models.py)."""
    defaults = dict(
        plugin_id="acme_widgets",
        name="Acme Widgets",
        description="A widget plugin",
        type="local",
        tier="premium",
        icon="🔧",
        version="1.0.0",
        remote_url="",
        auth_type="none",
        api_prefix="/acme-widgets",
        tags_list=[],
        scopes_list=[],
        manifest_url="",
        enabled=True,
        download_url="https://example.com/acme_widgets.tar.gz",
        install_path="",
        router_module="",
        router_attr="router",
        model_modules_list=[],
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class _FakeQueryResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    """Returns a fixed row list regardless of the select() statement passed in."""

    def __init__(self, rows):
        self._rows = rows

    def exec(self, stmt):
        return _FakeQueryResult(self._rows)


def _cleanup_modules(*names: str) -> None:
    for mod_name in list(sys.modules):
        if any(mod_name == n or mod_name.startswith(n + ".") for n in names):
            del sys.modules[mod_name]


# ---------------------------------------------------------------------------
# Happy path — flat router_module ("router") at the package root
# ---------------------------------------------------------------------------

class TestLoadDynamicLocalPlugin:

    def test_loads_flat_router_module(self, tmp_path, monkeypatch):
        """install_path/<unique>.py with router_module='<unique>' mounts via load_dynamic_plugins().

        Uses a plugin-specific module name (not the generic "router") because
        _ensure_on_syspath(install_dir) adds every install dir to sys.path
        permanently for the life of the process — a generic top-level module
        name like "router" would collide across multiple type=local plugins
        (whichever install dir comes first on sys.path wins). Vendors should
        pick a unique flat module name, or use the subpackage convention
        (see test_loads_subpackage_router_module) where the package name is
        naturally unique per plugin_id.
        """
        from fastapi import APIRouter
        from app.plugin_loader import load_dynamic_plugins

        install_dir = tmp_path / "acme_widgets-1.0.0"
        install_dir.mkdir()
        (install_dir / "acme_widgets_router.py").write_text(
            "from fastapi import APIRouter\nrouter = APIRouter()\n\n"
            "@router.get('/ping')\ndef ping():\n    return {'ok': True}\n"
        )
        (install_dir / "plugin.yaml").write_text(
            "id: acme_widgets\nname: Acme Widgets\nrouter_module: acme_widgets_router\n"
        )

        row = _local_row(install_path=str(install_dir), router_module="acme_widgets_router")
        session = _FakeSession([row])

        try:
            loaded = load_dynamic_plugins(session)
        finally:
            _cleanup_modules("acme_widgets_router")

        assert len(loaded) == 1
        plugin = loaded[0]
        assert plugin.manifest.id == "acme_widgets"
        assert plugin.manifest.type == "local"
        assert plugin.manifest.router_module == "acme_widgets_router"
        assert isinstance(plugin.router, APIRouter)
        assert any(r.path == "/ping" for r in plugin.router.routes)

    def test_loads_subpackage_router_module(self, tmp_path):
        """install_path/acme_widgets/router.py with router_module='acme_widgets.router' also mounts."""
        from fastapi import APIRouter
        from app.plugin_loader import load_dynamic_plugins

        install_dir = tmp_path / "acme_widgets-2.0.0"
        pkg_dir = install_dir / "acme_widgets"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "__init__.py").write_text("")
        (pkg_dir / "router.py").write_text(
            "from fastapi import APIRouter\nrouter = APIRouter()\n"
        )
        (install_dir / "plugin.yaml").write_text(
            "id: acme_widgets\nname: Acme Widgets\nrouter_module: acme_widgets.router\n"
        )

        row = _local_row(
            plugin_id="acme_widgets", version="2.0.0",
            install_path=str(install_dir), router_module="acme_widgets.router",
        )
        session = _FakeSession([row])

        try:
            loaded = load_dynamic_plugins(session)
        finally:
            _cleanup_modules("acme_widgets")

        assert len(loaded) == 1
        assert isinstance(loaded[0].router, APIRouter)


# ---------------------------------------------------------------------------
# Resilience — corrupted / missing installs must not crash startup
# ---------------------------------------------------------------------------

class TestCorruptedInstallSkipped:

    def test_missing_router_module_skipped_without_crash(self, tmp_path):
        """No router.py / no importable router_module — logged and skipped."""
        from app.plugin_loader import load_dynamic_plugins

        install_dir = tmp_path / "broken_plugin-1.0.0"
        install_dir.mkdir()
        # plugin.yaml present, but no broken_plugin_router.py — router_module won't import.
        (install_dir / "plugin.yaml").write_text(
            "id: broken_plugin\nname: Broken Plugin\nrouter_module: broken_plugin_router\n"
        )

        row = _local_row(
            plugin_id="broken_plugin",
            install_path=str(install_dir),
            router_module="broken_plugin_router",
        )
        session = _FakeSession([row])

        loaded = load_dynamic_plugins(session)
        assert loaded == []

    def test_missing_install_dir_skipped_without_crash(self, tmp_path):
        """install_path no longer exists on disk — logged and skipped."""
        from app.plugin_loader import load_dynamic_plugins

        row = _local_row(
            plugin_id="vanished_plugin",
            install_path=str(tmp_path / "vanished_plugin-1.0.0"),
            router_module="vanished_plugin_router",
        )
        session = _FakeSession([row])

        loaded = load_dynamic_plugins(session)
        assert loaded == []

    def test_router_attr_missing_skipped_without_crash(self, tmp_path):
        """router.py exists but has no 'router' attribute — AttributeError caught."""
        from app.plugin_loader import load_dynamic_plugins

        install_dir = tmp_path / "no_router_attr-1.0.0"
        install_dir.mkdir()
        (install_dir / "no_router_attr_router.py").write_text("# no 'router' defined here\n")
        (install_dir / "plugin.yaml").write_text(
            "id: no_router_attr\nname: No Router Attr\nrouter_module: no_router_attr_router\n"
        )

        row = _local_row(
            plugin_id="no_router_attr",
            install_path=str(install_dir),
            router_module="no_router_attr_router",
        )
        session = _FakeSession([row])

        try:
            loaded = load_dynamic_plugins(session)
        finally:
            _cleanup_modules("no_router_attr_router")

        assert loaded == []


# ---------------------------------------------------------------------------
# GC sweep — runs after the load loop, removes orphaned install directories
# ---------------------------------------------------------------------------

class TestGcSweepAfterLoad:

    def test_orphaned_install_removed_after_load(self, tmp_path, monkeypatch):
        """A directory not referenced by any enabled row is removed by the
        post-load GC sweep — the mechanism behind both uninstall cleanup
        (row hard-deleted) and post-update orphan cleanup (old version dir)."""
        import app.plugin_installer as pi
        from app.plugin_loader import load_dynamic_plugins

        monkeypatch.setattr(pi, "DYNAMIC_PLUGINS_ROOT", tmp_path)

        active_dir = tmp_path / "acme_widgets-1.0.0"
        active_dir.mkdir()
        (active_dir / "acme_widgets_router.py").write_text(
            "from fastapi import APIRouter\nrouter = APIRouter()\n"
        )

        # Orphaned: e.g. the previous version after an update, or a row that
        # was uninstalled (hard-deleted) since the last load.
        orphan_dir = tmp_path / "acme_widgets-0.9.0"
        orphan_dir.mkdir()

        row = _local_row(install_path=str(active_dir), router_module="acme_widgets_router")
        session = _FakeSession([row])

        try:
            load_dynamic_plugins(session)
        finally:
            _cleanup_modules("acme_widgets_router")

        assert active_dir.exists()
        assert not orphan_dir.exists()

    def test_no_enabled_rows_removes_all_install_dirs(self, tmp_path, monkeypatch):
        """If every row was uninstalled, the next load sweeps all leftover dirs."""
        import app.plugin_installer as pi
        from app.plugin_loader import load_dynamic_plugins

        monkeypatch.setattr(pi, "DYNAMIC_PLUGINS_ROOT", tmp_path)

        leftover_dir = tmp_path / "acme_widgets-1.0.0"
        leftover_dir.mkdir()

        session = _FakeSession([])
        loaded = load_dynamic_plugins(session)

        assert loaded == []
        assert not leftover_dir.exists()


# ---------------------------------------------------------------------------
# model_modules — always empty for type=local rows (v1 restriction)
# ---------------------------------------------------------------------------

class TestModelModulesAlwaysEmpty:

    def test_local_row_model_modules_is_noop_for_load_plugin_models(self, tmp_path):
        """model_modules_list is always [] for type=local; load_plugin_models()
        is a safe no-op even if ever called against a dynamic-plugin manifest."""
        from app.plugin_loader import load_dynamic_plugins, load_plugin_models

        install_dir = tmp_path / "acme_widgets-1.0.0"
        install_dir.mkdir()
        (install_dir / "acme_widgets_router.py").write_text(
            "from fastapi import APIRouter\nrouter = APIRouter()\n"
        )

        row = _local_row(install_path=str(install_dir), router_module="acme_widgets_router")
        session = _FakeSession([row])

        try:
            loaded = load_dynamic_plugins(session)
        finally:
            _cleanup_modules("acme_widgets_router")

        assert loaded[0].manifest.model_modules == []
        load_plugin_models([loaded[0].manifest])  # must not raise / import anything
