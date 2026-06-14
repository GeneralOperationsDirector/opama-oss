"""
Plugin Store API — community marketplace discovery + dynamic plugin management.

Endpoints:
    GET  /plugin-store/marketplace   — browse community plugins (fetched from registry URL)
    GET  /plugin-store/installed     — list dynamically-installed plugins
    POST /plugin-store/install       — install a remote plugin from a manifest URL
    DELETE /plugin-store/{plugin_id} — uninstall (disable) a dynamic plugin
    GET  /plugin-store/public-key    — this instance's RSA public key (for vendor verification)

Marketplace registry:
    The catalog of installable modules is a JSON array (see registry.json at the
    repo root). It is loaded from two sources and merged:
      - the local copy shipped in the image / repo (`MARKETPLACE_REGISTRY_FILE`,
        default <repo>/registry.json) — always available, even offline;
      - the remote copy at `MARKETPLACE_REGISTRY_URL` — lets new community
        modules appear without redeploying. Cached CACHE_TTL_SECONDS.
    The shipped catalog wins on id clash, so the trusted built-in entries can't
    be silently overridden by the remote registry; remote only *adds* entries.

Authentication:
    All write endpoints require an authenticated user (Firebase token).
    In a multi-user setup, restrict install/delete to admin users via role checks.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
import yaml
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from app.network_validators import assert_public_url
from services.auth.middleware import get_current_user, require_admin
from services.plugin_store.models import DynamicPlugin
from services.shared.audit import write_audit_log
from services.shared.database import get_session
from services.shared.models import User

router = APIRouter(prefix="/plugin-store", tags=["plugin-store"])

MARKETPLACE_REGISTRY_URL = os.getenv(
    "MARKETPLACE_REGISTRY_URL",
    "https://raw.githubusercontent.com/GeneralOperationsDirector/opama-oss/main/registry.json",
)
# Local copy of the catalog shipped with the app (repo root → /app/registry.json
# in the container via Dockerfile COPY + compose mount). Used offline and as the
# trusted base the remote registry is merged onto.
MARKETPLACE_REGISTRY_FILE = os.getenv(
    "MARKETPLACE_REGISTRY_FILE",
    str(Path(__file__).resolve().parents[2] / "registry.json"),
)
CACHE_TTL_SECONDS = 300  # 5 minutes

_registry_cache: list[dict] | None = None
_registry_cache_at: float = 0.0


def _load_local_registry() -> list[dict]:
    """Load the catalog shipped in the repo (registry.json). Never raises."""
    try:
        with open(MARKETPLACE_REGISTRY_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
        return [e for e in data if isinstance(e, dict)] if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []



# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class MarketplaceEntry(BaseModel):
    id: str
    name: str
    description: str = ""
    version: str = "1.0.0"
    tier: str = "free"
    type: str = "remote"
    icon: str = ""
    author: str = ""
    repo: str = ""
    manifest_url: str = ""
    category: str = ""
    tags: list[str] = []
    enable_plugins: str = ""  # for type=builtin: comma-separated service IDs to add to ENABLED_PLUGINS


class InstalledPluginOut(BaseModel):
    plugin_id: str
    name: str
    description: str
    type: str
    tier: str
    icon: str
    version: str
    remote_url: str
    auth_type: str
    api_prefix: str
    tags: list[str]
    scopes: list[str]
    manifest_url: str
    download_url: str
    install_path: str
    enabled: bool
    installed_at: datetime
    status: str  # "active" | "restart_required"


class InstallRequest(BaseModel):
    manifest_url: str
    plugin_id: Optional[str] = None  # override the ID from the manifest


class InstallResult(BaseModel):
    plugin_id: str
    name: str
    status: str  # "installed_restart_required" | "already_installed" | "updated_restart_required"
    message: str


class PipInstallRequest(BaseModel):
    package: str  # PEP 440 package spec, e.g. "opama-my-module==1.2.0"


class PipInstallResult(BaseModel):
    package: str
    status: str  # "installed_restart_required"
    message: str


class PipModuleOut(BaseModel):
    plugin_id: str
    name: str
    description: str = ""
    version: str = ""
    tier: str = "free"
    icon: str = ""
    package: str
    package_version: str
    status: str  # "active" | "restart_required"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch_registry() -> list[dict]:
    global _registry_cache, _registry_cache_at
    if _registry_cache is not None and (time.time() - _registry_cache_at) < CACHE_TTL_SECONDS:
        return _registry_cache

    remote: list[dict] = []
    try:
        resp = httpx.get(MARKETPLACE_REGISTRY_URL, timeout=10.0, follow_redirects=True)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            remote = data
    except Exception:
        remote = _registry_cache or []  # use stale cache rather than nothing

    # Merge: the shipped catalog is the trusted base; the remote registry may
    # ADD new community modules but cannot override a shipped entry (local wins
    # on id clash), so a tampered registry can't silently mutate a built-in.
    local = _load_local_registry()
    local_ids = {e["id"] for e in local if "id" in e}
    merged = local + [e for e in remote if isinstance(e, dict) and e.get("id") not in local_ids]
    _registry_cache = merged
    _registry_cache_at = time.time()
    return _registry_cache


def _fetch_and_parse_manifest(url: str) -> dict:
    """Fetch a plugin.yaml from the given URL and return the parsed dict."""
    try:
        resp = httpx.get(url, timeout=10.0, follow_redirects=True)
        resp.raise_for_status()
    except httpx.RequestError as exc:
        raise HTTPException(502, detail=f"Could not fetch manifest: {exc}")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, detail=f"Manifest URL returned {exc.response.status_code}")

    text = resp.text

    # Try YAML first (covers .yaml, .yml, and raw GitHub URLs)
    try:
        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # Fallback: try JSON
    try:
        data = resp.json()
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    raise HTTPException(422, detail="Manifest must be valid YAML or JSON")


def _validate_manifest_basics(data: dict, url: str) -> None:
    """
    Raise 422 if the manifest is missing fields required for any plugin type.

    type=local gets an additional, more involved validation pass —
    plugin_installer.validate_local_manifest() — called separately from
    install_plugin() once the plugin_id is known (it also checks id-match).
    """
    required = ["id", "name"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        raise HTTPException(422, detail=f"Manifest missing required fields: {missing}")

    if data.get("type", "local") == "remote":
        if not data.get("remote_url"):
            raise HTTPException(422, detail="Remote plugin manifest must include 'remote_url'")
        if not data.get("api_prefix", "").startswith("/"):
            raise HTTPException(422, detail="Remote plugin manifest 'api_prefix' must start with '/'")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/active-plugins")
def get_active_plugins():
    """
    Return builtin module IDs that are currently active or pending restart.

    'active'  — module's service IDs are all loaded in this process.
    'pending' — module is in the overrides file but not yet loaded (restart required).
    """
    from app.plugin_loader import get_loaded_plugin_ids, _read_overrides, BUILTIN_MODULE_SERVICE_IDS
    active_service_ids = get_loaded_plugin_ids()
    override_module_ids = _read_overrides()

    def _is_active(module_id: str) -> bool:
        s_ids = BUILTIN_MODULE_SERVICE_IDS.get(module_id, [module_id])
        return all(s in active_service_ids for s in s_ids)

    active = [m for m in BUILTIN_MODULE_SERVICE_IDS if _is_active(m)]
    pending = [m for m in override_module_ids if not _is_active(m)]
    return {"active": sorted(active), "pending": sorted(pending)}


@router.post("/enable/{module_id}")
def enable_builtin_module(
    module_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Enable a built-in module by ID. Persists to the overrides file; takes effect on next restart."""
    from app.plugin_loader import save_enabled_override, BUILTIN_MODULE_SERVICE_IDS, get_loaded_plugin_ids
    if module_id not in BUILTIN_MODULE_SERVICE_IDS:
        raise HTTPException(404, detail=f"Unknown built-in module: {module_id}")
    save_enabled_override(module_id)
    service_ids = BUILTIN_MODULE_SERVICE_IDS[module_id]
    active_ids = get_loaded_plugin_ids()
    already_active = all(s in active_ids for s in service_ids)
    write_audit_log(
        session,
        action="module.enable_builtin",
        user=current_user,
        target=module_id,
        request=request,
        detail="already active" if already_active else "restart required to activate",
    )
    return {
        "module_id": module_id,
        "status": "active" if already_active else "restart_required",
    }


@router.delete("/enable/{module_id}", status_code=204)
def disable_builtin_module(
    module_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Remove a built-in module from the persistent overrides file. Takes effect on next restart."""
    from app.plugin_loader import remove_enabled_override
    remove_enabled_override(module_id)
    write_audit_log(
        session,
        action="module.disable_builtin",
        user=current_user,
        target=module_id,
        request=request,
        detail="removed from overrides; restart required",
    )


@router.post("/restart")
def restart_server(
    request: Request,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Restart the API server process. Docker will restart the container automatically."""
    import threading
    import os as _os
    write_audit_log(
        session,
        action="system.restart",
        user=current_user,
        target="api",
        request=request,
        detail="restart triggered via plugin store",
    )

    def _exit():
        import time
        time.sleep(0.5)  # allow response to return before exiting
        _os._exit(0)

    threading.Thread(target=_exit, daemon=True).start()
    return {"status": "restarting"}


@router.post("/pip-install", response_model=PipInstallResult)
def pip_install_module(
    req: PipInstallRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    Install a pip package into /app/pip-modules and append it to requirements-modules.txt.

    The package must register 'opama.modules' entry points — see discover_entry_point_modules()
    in app/plugin_loader.py. The module becomes active on next server restart.

    Package name is validated against PEP 440 safe characters; subprocess uses a list
    (no shell=True) so no injection is possible even if the regex were bypassed.
    """
    import re
    import subprocess

    # Allow PEP 440 identifiers + version specifiers. No whitespace, quotes, or shell chars.
    if not re.match(r"^[a-zA-Z0-9._\-\[\]!<>=,~]+$", req.package):
        raise HTTPException(422, detail="Invalid package specification. Use a standard PEP 440 package name.")

    pip_modules_dir = Path("/app/pip-modules")
    pip_modules_dir.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        ["pip", "install", req.package, "--target", str(pip_modules_dir), "-q"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise HTTPException(500, detail=f"pip install failed: {result.stderr.strip() or result.stdout.strip()}")

    # Append to requirements-modules.txt if not already present
    req_file = Path("/app/requirements-modules.txt")
    existing_lines = req_file.read_text().splitlines() if req_file.exists() else []
    pkg_base = req.package.split("==")[0].split(">=")[0].split("<=")[0].strip()
    already_listed = any(
        line.strip().split("==")[0].split(">=")[0].split("<=")[0].strip() == pkg_base
        for line in existing_lines
        if line.strip() and not line.strip().startswith("#")
    )
    if not already_listed:
        with open(req_file, "a") as f:
            f.write(f"{req.package}\n")

    write_audit_log(
        session,
        action="plugin.pip_install",
        user=current_user,
        target=req.package,
        request=request,
        detail=f"pip installed {req.package} → {pip_modules_dir}",
    )

    return PipInstallResult(
        package=req.package,
        status="installed_restart_required",
        message=f"'{req.package}' installed. Restart the server to activate it.",
    )


@router.get("/pip-modules", response_model=list[PipModuleOut])
def list_pip_modules(_: User = Depends(get_current_user)):
    """
    List pip packages installed via /plugin-store/pip-install (entry points
    in the 'opama.modules' group), with active/restart_required status.

    A module shows 'active' once its router is mounted in this process
    (after the restart that follows install); otherwise 'restart_required'.
    """
    from app.plugin_loader import entry_point_modules_info
    return entry_point_modules_info()


@router.delete("/pip-modules/{package}", status_code=204)
def uninstall_pip_module(
    package: str,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
):
    """
    Remove a pip-installed module: delete its files from /app/pip-modules and
    drop it from requirements-modules.txt.

    Its router stays mounted in the running process (like a freshly-disabled
    dynamic plugin) until the next restart. Refuses to touch any distribution
    not located inside /app/pip-modules, so core dependencies on the base
    image can't be removed this way.
    """
    import importlib.metadata as importlib_metadata

    pip_modules_dir = Path("/app/pip-modules").resolve()

    try:
        dist = importlib_metadata.distribution(package)
    except importlib_metadata.PackageNotFoundError:
        raise HTTPException(404, detail=f"Package '{package}' not found")

    dist_root = Path(str(dist.locate_file(""))).resolve()
    if dist_root != pip_modules_dir and pip_modules_dir not in dist_root.parents:
        raise HTTPException(
            422,
            detail=f"'{package}' is not a pip-module (not installed under {pip_modules_dir})",
        )

    removed_dirs: set[Path] = set()
    for entry in dist.files or []:
        file_path = Path(str(dist.locate_file(entry))).resolve()
        if pip_modules_dir not in file_path.parents:
            continue  # safety: never touch anything outside pip-modules
        if file_path.is_file() or file_path.is_symlink():
            file_path.unlink(missing_ok=True)
        removed_dirs.add(file_path.parent)

    dist_info_dir = getattr(dist, "_path", None)
    if dist_info_dir is not None:
        dist_info_dir = Path(str(dist_info_dir)).resolve()
        if dist_info_dir.exists() and pip_modules_dir in dist_info_dir.parents:
            shutil.rmtree(dist_info_dir, ignore_errors=True)

    for d in sorted(removed_dirs, key=lambda p: len(p.parts), reverse=True):
        try:
            if d.exists() and pip_modules_dir in d.parents and not any(d.iterdir()):
                d.rmdir()
        except OSError:
            pass

    req_file = Path("/app/requirements-modules.txt")
    if req_file.exists():
        pkg_norm = package.lower().replace("_", "-")
        lines = req_file.read_text().splitlines()
        kept = [
            line for line in lines
            if not (
                line.strip()
                and not line.strip().startswith("#")
                and line.strip().split("==")[0].split(">=")[0].split("<=")[0].strip().lower().replace("_", "-") == pkg_norm
            )
        ]
        req_file.write_text("\n".join(kept) + ("\n" if kept else ""))

    write_audit_log(
        session,
        action="plugin.pip_uninstall",
        user=current_user,
        target=package,
        request=request,
        detail=f"removed pip module '{package}' from {pip_modules_dir}",
    )


@router.get("/marketplace", response_model=list[MarketplaceEntry])
def browse_marketplace(_: User = Depends(get_current_user)):  # browse is read-only, any user
    """Browse modules from the merged registry (shipped registry.json + remote)."""
    entries = _fetch_registry()
    return [MarketplaceEntry(**e) for e in entries if isinstance(e, dict)]


@router.get("/installed", response_model=list[InstalledPluginOut])
def list_installed(
    session: Session = Depends(get_session),
    _: User = Depends(get_current_user),
):
    """List all installed/enabled modules — builtin (overrides file) + dynamic (DB)."""
    from app.plugin_loader import get_loaded_plugin_ids, _read_overrides, BUILTIN_MODULE_SERVICE_IDS

    active_service_ids = get_loaded_plugin_ids()
    override_module_ids = _read_overrides()

    def _builtin_status(module_id: str) -> str:
        s_ids = BUILTIN_MODULE_SERVICE_IDS.get(module_id, [module_id])
        return "active" if all(s in active_service_ids for s in s_ids) else "restart_required"

    bundled_by_id = {e["id"]: e for e in _load_local_registry()}

    # Builtin modules enabled via the Plugin Store (from overrides file)
    builtin_rows = [
        InstalledPluginOut(
            plugin_id=mid,
            name=bundled_by_id.get(mid, {}).get("name", mid),
            description=bundled_by_id.get(mid, {}).get("description", ""),
            type="builtin",
            tier=bundled_by_id.get(mid, {}).get("tier", "premium"),
            icon=bundled_by_id.get(mid, {}).get("icon", ""),
            version=bundled_by_id.get(mid, {}).get("version", "1.0.0"),
            remote_url="",
            auth_type="",
            api_prefix="",
            tags=bundled_by_id.get(mid, {}).get("tags", []),
            scopes=[],
            manifest_url="",
            download_url="",
            install_path="",
            enabled=True,
            installed_at=datetime.now(timezone.utc),
            status=_builtin_status(mid),
        )
        for mid in sorted(override_module_ids)
    ]

    # Dynamic plugins installed via manifest URL (DB rows)
    dynamic_rows = [
        InstalledPluginOut(
            plugin_id=p.plugin_id,
            name=p.name,
            description=p.description,
            type=p.type,
            tier=p.tier,
            icon=p.icon,
            version=p.version,
            remote_url=p.remote_url,
            auth_type=p.auth_type,
            api_prefix=p.api_prefix,
            tags=p.tags_list,
            scopes=p.scopes_list,
            manifest_url=p.manifest_url,
            download_url=p.download_url,
            install_path=p.install_path,
            enabled=p.enabled,
            installed_at=p.installed_at,
            status="active" if p.enabled else "restart_required",
        )
        for p in session.exec(select(DynamicPlugin)).all()
    ]

    return builtin_rows + dynamic_rows


@router.post("/install", response_model=InstallResult)
def install_plugin(
    req: InstallRequest,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
):
    """
    Install a plugin from a manifest URL (YAML or JSON).

    type=remote: opama proxies to the vendor's hosted service; the route is
        registered on the next app restart (X-Opama-Plugin-Token auth).
    type=local: the package's code is downloaded, safely extracted into
        DYNAMIC_PLUGINS_ROOT, and imported in-process on the next restart —
        see app/plugin_installer.py for the full download/extraction pipeline
        and the license-gating + SSRF + safe-extraction guarantees involved.

    Either way, returns status='installed_restart_required' / 'updated_restart_required'
    so the caller knows a restart is needed to activate the plugin.
    """
    # SSRF: manifest URL must resolve to a public address
    try:
        assert_public_url(req.manifest_url, "Manifest URL")
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    data = _fetch_and_parse_manifest(req.manifest_url)
    _validate_manifest_basics(data, req.manifest_url)

    plugin_id = req.plugin_id or data["id"]

    # Normalise the plugin_id to a safe identifier
    plugin_id = plugin_id.strip().lower().replace("-", "_")

    # Branch on the freshly-fetched manifest's type/tier — never a cached
    # MarketplaceEntry. A vendor could under-report tier in the public
    # registry to dodge the license gate below, then ship a heavier payload
    # once past it; re-deriving from the manifest we just fetched closes that.
    manifest_type = data.get("type", "remote")
    manifest_tier = data.get("tier", "free")
    manifest_version = data.get("version", "1.0.0")

    existing = session.exec(
        select(DynamicPlugin).where(DynamicPlugin.plugin_id == plugin_id)
    ).first()

    download_url = data.get("download_url", "")
    router_module = data.get("router_module", "")
    router_attr = data.get("router_attr", "router")
    install_path = existing.install_path if existing else ""
    new_install_dir: Optional[Path] = None

    if manifest_type == "local":
        from app.license import get_license
        from app.plugin_installer import (
            DYNAMIC_PLUGINS_ROOT,
            download_and_extract,
            mint_download_token,
            validate_local_manifest,
        )

        # Fail fast on license entitlement — before validating or spending
        # any bandwidth on the download. Tone mirrors DashboardView's
        # "Upgrade to unlock" copy for premium-gated modules.
        license_info = get_license()
        if not license_info.allows_plugin(plugin_id, manifest_tier):
            raise HTTPException(
                403,
                detail=(
                    f"Upgrade to unlock '{data.get('name', plugin_id)}' — "
                    "your current plan doesn't include this plugin"
                ),
            )

        validate_local_manifest(data, plugin_id)

        token = mint_download_token(plugin_id, manifest_tier)
        final_path, _extracted_manifest = download_and_extract(
            plugin_id, manifest_version, download_url, token, DYNAMIC_PLUGINS_ROOT,
        )
        new_install_dir = final_path
        install_path = str(final_path)

    tags = data.get("tags", [])
    scopes = data.get("scopes", [])
    local_detail_suffix = f" — downloaded {download_url} to {install_path}" if manifest_type == "local" else ""

    try:
        if existing:
            # Update in place
            existing.name = data["name"]
            existing.description = data.get("description", "")
            existing.type = manifest_type
            existing.tier = manifest_tier
            existing.icon = data.get("icon", "")
            existing.version = manifest_version
            existing.remote_url = data.get("remote_url", "")
            existing.auth_type = data.get("auth_type", "none")
            existing.api_prefix = data.get("api_prefix", f"/{plugin_id}")
            existing.tags_json = json.dumps(tags if isinstance(tags, list) else [])
            existing.scopes_json = json.dumps(scopes if isinstance(scopes, list) else [])
            existing.manifest_url = req.manifest_url
            existing.download_url = download_url
            existing.install_path = install_path
            existing.router_module = router_module
            existing.router_attr = router_attr
            existing.model_modules_json = "[]"
            existing.enabled = True
            session.add(existing)
            session.commit()
        else:
            plugin = DynamicPlugin(
                plugin_id=plugin_id,
                name=data["name"],
                description=data.get("description", ""),
                type=manifest_type,
                tier=manifest_tier,
                icon=data.get("icon", ""),
                version=manifest_version,
                remote_url=data.get("remote_url", ""),
                auth_type=data.get("auth_type", "none"),
                api_prefix=data.get("api_prefix", f"/{plugin_id}"),
                tags_json=json.dumps(tags if isinstance(tags, list) else []),
                scopes_json=json.dumps(scopes if isinstance(scopes, list) else []),
                manifest_url=req.manifest_url,
                download_url=download_url,
                install_path=install_path,
                router_module=router_module,
                router_attr=router_attr,
                model_modules_json="[]",
                enabled=True,
            )
            session.add(plugin)
            session.commit()
    except Exception:
        # A post-extraction DB failure (or race) must not orphan a freshly
        # downloaded package on disk — clean it up rather than leaving it
        # for the GC sweep to (eventually) discover at next startup.
        if new_install_dir is not None and new_install_dir.exists():
            shutil.rmtree(new_install_dir, ignore_errors=True)
        raise

    if existing:
        write_audit_log(
            session,
            action="plugin.update",
            user=current_user,
            target=plugin_id,
            request=request,
            detail=f"updated to v{existing.version} from {req.manifest_url}{local_detail_suffix}",
        )
        return InstallResult(
            plugin_id=plugin_id,
            name=existing.name,
            status="updated_restart_required",
            message="Plugin updated. Restart the API server to activate the new version.",
        )

    write_audit_log(
        session,
        action="plugin.install",
        user=current_user,
        target=plugin_id,
        request=request,
        detail=f"installed v{manifest_version} ({manifest_type}) from {req.manifest_url}{local_detail_suffix}",
    )

    return InstallResult(
        plugin_id=plugin_id,
        name=data["name"],
        status="installed_restart_required",
        message="Plugin installed. Restart the API server to activate it.",
    )


@router.delete("/{plugin_id}", status_code=204)
def uninstall_plugin(
    plugin_id: str,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_admin),
):
    """
    Uninstall (permanently delete) a dynamic plugin. Admin only — mirrors install.

    For type=local rows this deletes only the DB row — never the on-disk
    package. Its module may still be imported and its router still mounted in
    the running process (exactly like a freshly-disabled remote plugin) until
    the next restart; rmtree-ing now risks mid-request file-not-found errors.
    Once this row is gone, _gc_orphaned_local_installs() (run at the next
    startup, after the load loop) finds the directory unreferenced by any
    enabled row and removes it then — one mechanism for both uninstall
    cleanup and orphaned-old-version cleanup after updates.
    """
    plugin = session.exec(
        select(DynamicPlugin).where(DynamicPlugin.plugin_id == plugin_id)
    ).first()
    if not plugin:
        raise HTTPException(404, detail=f"Plugin '{plugin_id}' not found")
    session.delete(plugin)
    session.commit()
    write_audit_log(
        session,
        action="plugin.uninstall",
        user=current_user,
        target=plugin_id,
        request=request,
        detail=f"uninstalled {plugin.name} v{plugin.version}",
    )


@router.get("/public-key")
def get_public_key(_: User = Depends(get_current_user)):
    """
    Return this instance's RSA public key in PEM format.

    Remote plugin vendors use this to verify X-Opama-Plugin-Token JWTs.
    """
    from app.plugin_signing import get_public_key_pem, get_instance_id
    return {
        "instance_id": get_instance_id(),
        "public_key_pem": get_public_key_pem(),
        "algorithm": "RS256",
    }
