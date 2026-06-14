"""
Plugin loader for opama.

Discovers service plugins by scanning services/*/plugin.yaml, plus any
directories named in PLUGIN_PATHS (for plugins whose code lives outside this
repo — see "External plugin discovery" below).
Reads ENABLED_PLUGINS env var to filter which plugins load at startup.

Two plugin types are supported:
  type: local  (default) — Python code is importable in-process; imported via importlib.
  type: remote           — Vendor hosts their own server; opama reverse-proxies via httpx.

External plugin discovery (PLUGIN_PATHS):
  Premium/community plugins don't have to live in services/ — this is the
  mechanism that makes the "repo split" (distributing modules from their own
  repos) possible without changing how plugins are authored or loaded. Each directory
  named in PLUGIN_PATHS (comma-separated, like ENABLED_PLUGINS) is treated as a
  "plugin root" that mirrors services/: its immediate subdirectories are plugin
  packages, each containing plugin.yaml directly inside, exactly like
  services/<id>/plugin.yaml. The package's parent directory is added to
  sys.path once so its dotted router_module/model_modules import normally.
  See external_plugins/opama_marketplace/ for the reference shape — a real
  premium plugin (eBay search) converted to this convention as a proof.

Remote plugin auth:
  auth_type: none        — No auth header added (default).
  auth_type: signed_jwt  — opama signs a short-lived RS256 JWT per request, sent as
                           X-Opama-Plugin-Token. Vendor validates with GET /plugin-store/public-key.

The user's Firebase token is always forwarded as X-Opama-User-Token on proxied requests
so vendors can call the opama REST API on the user's behalf.

Usage in main.py:
    from app.plugin_loader import discover_plugins, resolve_enabled, load_plugin_models, load_plugins

    _all     = discover_plugins()
    _enabled = resolve_enabled(_all)
    load_plugin_models(_enabled)
    for loaded in load_plugins(_enabled):
        app.include_router(loaded.router, prefix=loaded.manifest.api_prefix, tags=loaded.manifest.tags)

Dynamic plugins (from DB) are loaded separately after init_db():
    from app.plugin_loader import load_dynamic_plugins
    for loaded in load_dynamic_plugins(session):
        app.include_router(loaded.router, prefix=loaded.manifest.api_prefix, tags=loaded.manifest.tags)

  Two DB-driven shapes are supported, both installed via POST /plugin-store/install:
    type=remote — same hosted-proxy mechanism as a static remote manifest;
                  _make_remote_proxy_router() builds the catch-all router.
    type=local  — vendor's code was downloaded and safely extracted onto this
                  instance by app.plugin_installer.download_and_extract() at
                  install time, into DYNAMIC_PLUGINS_ROOT (default
                  /app/dynamic_plugins — deliberately NOT a PLUGIN_PATHS
                  entry; see app.plugin_installer module docstring for why
                  mixing the two loading paths would double-register the
                  package). load_dynamic_plugins() makes its contents
                  importable via _ensure_on_syspath(install_dir) — the
                  install dir itself (named "<plugin_id>-<version>", not a
                  valid dotted-path component) is added to sys.path, so
                  router_module is resolved *relative to the package root*
                  (e.g. "router" for a flat router.py, or "mypkg.router" for
                  a subpackage) — then router_attr is read off it. Restricted to
                  model_modules=[] in v1 (see app.plugin_installer and the
                  TODO near load_plugin_models() below for the two-layered
                  reason). A garbage-collection sweep
                  (_gc_orphaned_local_installs) runs after every load,
                  removing install directories no longer referenced by an
                  enabled row — the single mechanism behind both uninstall
                  cleanup and post-update orphan cleanup.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

SERVICES_DIR = Path(__file__).resolve().parents[1] / "services"

# Overrides file: marketplace module IDs the user has enabled via the Plugin Store UI.
# Lives in DYNAMIC_PLUGINS_ROOT (a persistent volume) so enables survive restarts.
_OVERRIDES_FILE = Path(os.getenv("DYNAMIC_PLUGINS_ROOT", "/app/dynamic_plugins")) / "enabled_overrides.json"

# Maps marketplace module IDs (as they appear in registry.json / enable/{id})
# to the backend service plugin IDs they activate. Keep the `enable_plugins`
# field of each builtin entry in registry.json in sync with this table.
BUILTIN_MODULE_SERVICE_IDS: dict[str, list[str]] = {
    "pokemon_tcg": ["catalog", "inventory", "decks", "trading"],
    "grading":     ["grading"],
    "portfolio":   ["portfolio"],
    "storefront":  ["storefront"],
    "ai":          ["ai", "decks"],
    "showcase":    ["showcase"],
}

# Tracks which plugin IDs are active in the current process.
# Populated by record_loaded_ids() after load_plugins() and load_dynamic_plugins().
_loaded_plugin_ids: set[str] = set()


def _read_overrides() -> set[str]:
    try:
        return set(json.loads(_OVERRIDES_FILE.read_text()))
    except Exception:
        return set()


def _write_overrides(ids: set[str]) -> None:
    _OVERRIDES_FILE.parent.mkdir(parents=True, exist_ok=True)
    _OVERRIDES_FILE.write_text(json.dumps(sorted(ids)))


def save_enabled_override(plugin_id: str) -> None:
    """Persist a user-enabled builtin plugin ID. Takes effect on next restart."""
    ids = _read_overrides()
    ids.add(plugin_id)
    _write_overrides(ids)


def remove_enabled_override(plugin_id: str) -> None:
    """Remove a builtin plugin ID from the persistent overrides."""
    ids = _read_overrides()
    ids.discard(plugin_id)
    _write_overrides(ids)


def record_loaded_ids(plugins: list[LoadedPlugin]) -> None:
    """Record which plugin IDs are active in this process. Called after load_plugins()."""
    _loaded_plugin_ids.update(p.manifest.id for p in plugins)


def get_loaded_plugin_ids() -> frozenset[str]:
    """Return the set of plugin IDs active in the current process."""
    return frozenset(_loaded_plugin_ids)


# Directories added to sys.path so external plugin packages become importable.
# Tracked to avoid inserting the same entry twice across repeated discovery calls.
_external_paths_on_syspath: set[str] = set()


def _external_plugin_roots() -> list[Path]:
    """Parse PLUGIN_PATHS (comma-separated, like ENABLED_PLUGINS) into existing dirs."""
    raw = os.getenv("PLUGIN_PATHS", "").strip()
    if not raw:
        return []
    roots = []
    for entry in raw.split(","):
        path = Path(entry.strip())
        if entry.strip() and path.is_dir():
            roots.append(path)
    return roots


@dataclass
class PluginManifest:
    id: str
    name: str
    version: str = "1.0.0"
    tier: str = "core"           # core | free | premium | enterprise
    type: str = "local"          # local | remote
    description: str = ""
    icon: str = ""
    api_prefix: str = ""
    tags: list[str] = field(default_factory=list)
    # local-only fields
    router_module: str = ""      # required for type=local
    router_attr: str = "router"
    model_modules: list[str] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)
    # remote-only fields
    remote_url: str = ""         # required for type=remote
    auth_type: str = "none"      # none | signed_jwt
    scopes: list[str] = field(default_factory=list)


@dataclass
class LoadedPlugin:
    manifest: PluginManifest
    router: "Any"  # APIRouter — typed as Any to avoid top-level FastAPI import


def discover_plugins() -> list[PluginManifest]:
    """
    Scan services/ for plugin.yaml manifests, plus any PLUGIN_PATHS roots
    (external plugin packages — see module docstring), sorted by directory name.
    Also discovers pip-installed packages that register opama.modules entry points
    (see discover_entry_point_modules()).

    Each PLUGIN_PATHS root's directory is added to sys.path so its plugin
    packages' router_module/model_modules dotted paths import normally —
    no different from how services.<id>.<module> resolves via PYTHONPATH=/app.
    """
    search_dirs = [SERVICES_DIR, *_external_plugin_roots()]

    manifests: list[PluginManifest] = []
    for search_dir in search_dirs:
        paths = sorted(search_dir.glob("*/plugin.yaml"))
        if search_dir != SERVICES_DIR:
            # Multi-plugin packages (e.g. external_plugins/opama_pokemon_tcg/, which
            # ships catalog/inventory/decks/trading as separate plugins) place their
            # plugin.yaml manifests one level deeper than single-plugin packages
            # (e.g. external_plugins/opama_marketplace/plugin.yaml).
            paths += sorted(search_dir.glob("*/*/plugin.yaml"))
        if search_dir != SERVICES_DIR and paths:
            _ensure_on_syspath(search_dir)
        for path in paths:
            with open(path) as f:
                data = yaml.safe_load(f)
            manifests.append(_manifest_from_dict(data))

    manifests.extend(discover_entry_point_modules())
    return manifests


def discover_entry_point_modules() -> list[PluginManifest]:
    """
    Discover modules registered via pip entry_points in the 'opama.modules' group.

    Pip packages installed with `pip install --target /app/pip-modules` place their
    .dist-info directories there; when /app/pip-modules is on sys.path (via PYTHONPATH),
    importlib.metadata finds those distributions and their entry points.

    Each entry point:
      name  — becomes the plugin ID
      value — dotted path to a callable (or dict) that returns a PluginManifest or dict

    Example pyproject.toml in a community module:
        [project.entry-points."opama.modules"]
        my_module = "my_package.plugin:get_manifest"
    """
    import logging
    log = logging.getLogger("uvicorn.error")

    try:
        from importlib.metadata import entry_points
    except ImportError:
        return []

    manifests: list[PluginManifest] = []
    try:
        eps = entry_points(group="opama.modules")
    except Exception:
        return []

    for ep in eps:
        try:
            obj = ep.load()
            data = obj() if callable(obj) else obj
            if isinstance(data, PluginManifest):
                manifests.append(data)
            elif isinstance(data, dict):
                manifests.append(_manifest_from_dict(data))
            else:
                log.warning("opama.modules entry point '%s' returned unexpected type %s", ep.name, type(data))
        except Exception as exc:
            log.warning("⚠️  Skipping pip entry point module '%s': %s", ep.name, exc)

    if manifests:
        log.info("🐍 Pip entry point modules found: %s", [m.id for m in manifests])

    return manifests


def entry_point_modules_info() -> list[dict]:
    """
    Describe pip packages registering 'opama.modules' entry points: which
    distribution (name + version) provides each module, and whether it's
    active in this process (get_loaded_plugin_ids()) or needs a restart to
    take effect.

    Used by GET /plugin-store/pip-modules. Kept separate from
    discover_entry_point_modules() (which builds the PluginManifests that
    discover_plugins() loads) because this needs distribution metadata that
    PluginManifest doesn't carry, and must keep going even if a single entry
    point's manifest factory raises — falling back to the entry point's own
    name/dist info so a broken module still shows up as uninstallable.
    """
    import logging
    log = logging.getLogger("uvicorn.error")

    try:
        from importlib.metadata import entry_points
    except ImportError:
        return []

    try:
        eps = entry_points(group="opama.modules")
    except Exception:
        return []

    active_ids = get_loaded_plugin_ids()
    results: list[dict] = []
    for ep in eps:
        manifest: PluginManifest | None = None
        try:
            obj = ep.load()
            data = obj() if callable(obj) else obj
            if isinstance(data, PluginManifest):
                manifest = data
            elif isinstance(data, dict):
                manifest = _manifest_from_dict(data)
        except Exception as exc:
            log.warning("⚠️  pip module entry point '%s' failed to load for status info: %s", ep.name, exc)

        plugin_id = manifest.id if manifest else ep.name
        dist = ep.dist
        results.append({
            "plugin_id": plugin_id,
            "name": manifest.name if manifest else ep.name,
            "description": manifest.description if manifest else "",
            "version": manifest.version if manifest else "",
            "tier": manifest.tier if manifest else "free",
            "icon": manifest.icon if manifest else "",
            "package": dist.name if dist else ep.name,
            "package_version": dist.version if dist else "",
            "status": "active" if plugin_id in active_ids else "restart_required",
        })
    return results


def _ensure_on_syspath(directory: Path) -> None:
    """Add `directory` to sys.path once, so packages inside it become importable."""
    key = str(directory.resolve())
    if key not in _external_paths_on_syspath:
        sys.path.insert(0, key)
        _external_paths_on_syspath.add(key)


def _manifest_from_dict(data: dict) -> PluginManifest:
    """Build a PluginManifest from a parsed plugin.yaml dict."""
    return PluginManifest(
        id=data["id"],
        name=data["name"],
        version=data.get("version", "1.0.0"),
        tier=data.get("tier", "core"),
        type=data.get("type", "local"),
        description=data.get("description", ""),
        icon=data.get("icon", ""),
        api_prefix=data.get("api_prefix", ""),
        tags=data.get("tags", []),
        router_module=data.get("router_module", ""),
        router_attr=data.get("router_attr", "router"),
        model_modules=data.get("model_modules", []),
        requires=data.get("requires", []),
        remote_url=data.get("remote_url", ""),
        auth_type=data.get("auth_type", "none"),
        scopes=data.get("scopes", []),
    )


def resolve_enabled(all_plugins: list[PluginManifest]) -> list[PluginManifest]:
    """
    Return plugins to load.

    Priority (first match wins):
    1. ENABLED_PLUGINS env var — explicit comma-separated list of plugin IDs.
    2. OPAMA_LICENSE_KEY env var — tier-based or module-list filtering.
    3. Default — all plugins enabled (dev / open mode).
    """
    raw = os.getenv("ENABLED_PLUGINS", "").strip()
    if raw:
        enabled_ids = {s.strip() for s in raw.split(",") if s.strip()}
        # Expand module IDs from the overrides file into their constituent service IDs.
        for module_id in _read_overrides():
            enabled_ids.update(BUILTIN_MODULE_SERVICE_IDS.get(module_id, [module_id]))
        return [p for p in all_plugins if p.id in enabled_ids]

    from app.license import get_license
    info = get_license()
    if info.valid:
        return [p for p in all_plugins if info.allows_plugin(p.id, p.tier)]

    if info.modules == "*":
        return all_plugins

    return [p for p in all_plugins if p.tier == "core"]


def load_plugin_models(plugins: list[PluginManifest]) -> None:
    """
    Import every model module declared by each local plugin.

    Must be called before init_db() / SQLModel.metadata.create_all() so that
    all table definitions are registered with SQLModel's metadata.

    TODO (documented future-work blocker — don't "fix" without re-reading
    this): DB-installed type=local plugins (app.plugin_installer,
    load_dynamic_plugins) are restricted to model_modules=[] precisely
    because they can't participate here. Two independent reasons: (1) this
    function runs at module-import time, before init_db()/create_all() and
    before the FastAPI app exists, while load_dynamic_plugins() runs a full
    lifecycle phase later inside @app.on_event("startup") against an
    already-initialized engine — querying dynamic_plugins early enough to
    matter would mean doing it before create_all(), entangling plugin
    discovery with DB bootstrap exactly as the comment block at the top of
    main.py says this codebase deliberately avoids; (2) even with ordering
    solved, create_all() only adds missing tables — production schemas are
    Alembic-managed (see migration_practices) — so running arbitrary
    third-party DDL at install time would be its own, separate security
    problem. Lifting the model_modules=[] restriction requires solving both.
    """
    for plugin in plugins:
        if plugin.type != "local":
            continue
        for module_path in plugin.model_modules:
            importlib.import_module(module_path)


def load_plugins(plugins: list[PluginManifest]) -> list[LoadedPlugin]:
    """
    Import / construct the router for each plugin and return LoadedPlugin instances.

    A plugin whose router module fails to import (e.g. it hard-imports
    another optional plugin's package that isn't on PLUGIN_PATHS for this
    deployment) is logged and skipped rather than raising — one
    misconfigured or incompatible plugin must not take down the whole app
    at startup. Mirrors load_dynamic_plugins()'s "log and skip" handling of
    a corrupted/incompatible install.
    """
    import logging
    log = logging.getLogger("uvicorn.error")

    loaded: list[LoadedPlugin] = []
    for manifest in plugins:
        try:
            if manifest.type == "remote":
                router = _make_remote_proxy_router(manifest)
            else:
                mod = importlib.import_module(manifest.router_module)
                router: Any = getattr(mod, manifest.router_attr)
        except Exception as exc:
            log.error(f"⚠️  Skipping plugin '{manifest.id}': failed to load {manifest.router_module} ({exc})")
            continue
        loaded.append(LoadedPlugin(manifest=manifest, router=router))
    return loaded


def load_dynamic_plugins(session) -> list[LoadedPlugin]:
    """
    Load plugins stored in the dynamic_plugins DB table — both type=remote
    (hosted-proxy) and type=local (downloaded code, imported in-process).

    Called during app startup (after init_db()) to register plugins that were
    installed via the plugin store API.

    For type=local rows, the package directory was placed under
    DYNAMIC_PLUGINS_ROOT by app.plugin_installer.download_and_extract() at
    install time (never via PLUGIN_PATHS — see module docstring "External
    plugin discovery": adding DYNAMIC_PLUGINS_ROOT there would make
    discover_plugins()'s glob find the same package this function loads from
    its DB row, double-registering it). _ensure_on_syspath() makes its dotted
    router_module importable, exactly as it does for PLUGIN_PATHS packages.
    A corrupted or incompatible install is logged and skipped rather than
    crashing startup.

    After the load loop, sweeps DYNAMIC_PLUGINS_ROOT for directories no
    longer referenced by an enabled row (uninstalls + orphaned old versions
    after updates) — see app.plugin_installer._gc_orphaned_local_installs.

    Returns LoadedPlugin instances ready for app.include_router().
    """
    try:
        from sqlmodel import select
        from services.plugin_store.models import DynamicPlugin
    except ImportError:
        return []

    import logging
    log = logging.getLogger("uvicorn.error")

    rows = session.exec(select(DynamicPlugin).where(DynamicPlugin.enabled == True)).all()
    loaded: list[LoadedPlugin] = []
    for row in rows:
        manifest = PluginManifest(
            id=row.plugin_id,
            name=row.name,
            version=row.version,
            tier=row.tier,
            type=row.type,
            description=row.description,
            icon=row.icon,
            api_prefix=row.api_prefix,
            tags=row.tags_list,
            router_module=row.router_module,
            router_attr=row.router_attr,
            model_modules=row.model_modules_list,
            remote_url=row.remote_url,
            auth_type=row.auth_type,
            scopes=row.scopes_list,
        )
        if manifest.type == "remote":
            router = _make_remote_proxy_router(manifest)
            loaded.append(LoadedPlugin(manifest=manifest, router=router))
        elif manifest.type == "local":
            try:
                install_dir = Path(row.install_path)
                _ensure_on_syspath(install_dir)
                mod = importlib.import_module(manifest.router_module)
                router = getattr(mod, manifest.router_attr)
            except (ImportError, AttributeError, OSError) as exc:
                log.warning(
                    "⚠️  Skipping local dynamic plugin '%s' — failed to load %s:%s (%s)",
                    row.plugin_id, manifest.router_module, manifest.router_attr, exc,
                )
                continue
            loaded.append(LoadedPlugin(manifest=manifest, router=router))

    try:
        from app.plugin_installer import DYNAMIC_PLUGINS_ROOT, _gc_orphaned_local_installs
        _gc_orphaned_local_installs(session, DYNAMIC_PLUGINS_ROOT)
    except ImportError:
        pass

    return loaded


def _make_remote_proxy_router(manifest: PluginManifest) -> Any:
    """
    Build a catch-all APIRouter that reverse-proxies all requests to manifest.remote_url.

    Auth headers added to every proxied request:
      X-Opama-User-Token  — the original Firebase Bearer token (for calling opama API)
      X-Opama-Plugin-Token — short-lived RS256 JWT (only when auth_type=signed_jwt)
    """
    import httpx
    from fastapi import APIRouter, HTTPException, Request
    from fastapi.responses import Response

    plugin_id = manifest.id
    remote_url = manifest.remote_url.rstrip("/")
    auth_type = manifest.auth_type

    router = APIRouter()

    @router.api_route(
        "/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    )
    async def _proxy(request: Request, path: str):
        target = f"{remote_url}/{path}" if path else remote_url

        # Build headers — strip hop-by-hop
        _skip = {"host", "content-length", "transfer-encoding", "connection"}
        fwd_headers = {k: v for k, v in request.headers.items() if k.lower() not in _skip}

        # Forward Firebase token for calling opama REST API as the user
        if auth := request.headers.get("authorization"):
            fwd_headers["x-opama-user-token"] = auth

        # Sign a plugin auth token when the manifest requires it
        if auth_type == "signed_jwt":
            from app.plugin_signing import sign_plugin_token, _extract_user_id
            user_id = _extract_user_id(request.headers.get("authorization", ""))
            fwd_headers["x-opama-plugin-token"] = sign_plugin_token(user_id, plugin_id)

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.request(
                    method=request.method,
                    url=target,
                    headers=fwd_headers,
                    params=dict(request.query_params),
                    content=await request.body(),
                )
            except httpx.RequestError as exc:
                raise HTTPException(502, detail=f"Remote plugin '{plugin_id}' unreachable: {exc}")

        # Strip response hop-by-hop headers
        _resp_skip = {"content-encoding", "transfer-encoding", "connection"}
        resp_headers = {k: v for k, v in resp.headers.items() if k.lower() not in _resp_skip}

        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=resp_headers,
        )

    return router


def list_enabled_ids(plugins: list[PluginManifest]) -> list[str]:
    """Convenience: return just the IDs of a resolved plugin list."""
    return [p.id for p in plugins]
