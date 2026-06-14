"""
Local plugin code-download installer.

Implements the "download-and-run-in-process" half of the marketplace,
complementing the type=remote hosted-proxy mechanism in
plugin_loader._make_remote_proxy_router(): fetches a vendor-hosted archive,
safely extracts it onto disk, and returns enough metadata for the plugin
store router to persist a DynamicPlugin row that load_dynamic_plugins() can
import and mount on the next restart.

Security model:
  - download_url is just as attacker-influenceable as manifest_url/remote_url
    (vendor-controlled, surfaced via the public marketplace registry) — SSRF
    guarded with assert_public_url, exactly like those are elsewhere in
    plugin_store.
  - The archive itself is attacker-influenceable — extraction runs the full
    safe-extraction pipeline below: format sniffing (never trust the URL's
    extension), path-traversal rejection (resolve-then-compare, never
    string-prefix), symlink/hardlink/device rejection, cumulative
    extracted-byte + member-count caps (zip-bomb defense — distinct from the
    compressed-size cap on the download itself), permission-bit stripping,
    and atomic placement (a partially-extracted directory is never visible
    to the loader).
  - Downloads are authenticated with a short-lived signed token
    (mint_download_token) so a vendor can verify "this request comes from a
    legitimately-licensed opama instance" and gate by tier — symmetric to
    the X-Opama-Plugin-Token proxy pattern, but with a distinct claim shape
    (`tier` instead of `user_id`; see plugin_signing.py's module docstring).

v1 restriction — model_modules must be empty:
  Local installs are restricted to plugins with zero new DB models. Two
  independent reasons (both worth restating here since this module is where
  the restriction is enforced):
    1. Import ordering — load_plugin_models() runs at module-import time in
       main.py, before init_db()/create_all() and before the FastAPI app
       object exists, so SQLModel sees the tables. load_dynamic_plugins()
       runs a full lifecycle phase later, inside the @app.on_event("startup")
       handler, against an already-initialized engine.
    2. Migration-on-install — even if ordering were solved, create_all()
       only creates tables that don't exist yet; production schemas are
       Alembic-managed (see migration_practices). Running arbitrary
       third-party DDL against an instance's database at install time is a
       wholly separate security problem.
  This mirrors exactly why `marketplace` (zero DB tables) was chosen as the
  static PLUGIN_PATHS proof-of-concept — same "lowest blast radius"
  reasoning, applied consistently. validate_local_manifest() enforces this
  with a 422 at install time.
"""
from __future__ import annotations

import logging
import os
import shutil
import stat
import tarfile
import tempfile
import zipfile
from pathlib import Path

import httpx
import yaml
from fastapi import HTTPException

from app.network_validators import assert_public_url
from app.plugin_signing import _sign

logger = logging.getLogger(__name__)

DYNAMIC_PLUGINS_ROOT = Path(os.getenv("DYNAMIC_PLUGINS_ROOT", "/app/dynamic_plugins"))

# Generous enough for real plugin packages, tight enough to bound worst-case
# disk/memory use against a malicious or compromised vendor server.
MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024        # 50 MB compressed, streamed-and-capped
MAX_EXTRACTED_BYTES = 200 * 1024 * 1024      # 200 MB uncompressed — zip-bomb cap
MAX_MEMBERS = 5_000

# Sized for "time to *initiate* the download," not the full transfer — most
# servers validate the Authorization header once at request-start and stream
# the body after, so 15 minutes covers slow connections without needing
# replay protection (consistent with the existing 60s proxy token's risk
# tolerance — see plugin_signing.sign_plugin_token).
DOWNLOAD_TOKEN_TTL_SECONDS = 15 * 60

# Files written during extraction get rw-r--r-- regardless of what the
# archive claims — never trust vendor-supplied setuid/setgid/sticky bits.
_EXTRACTED_FILE_MODE = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH


# ---------------------------------------------------------------------------
# Download-token minting
# ---------------------------------------------------------------------------

def mint_download_token(plugin_id: str, tier: str, *, ttl_seconds: int = DOWNLOAD_TOKEN_TTL_SECONDS) -> str:
    """
    Return a short-lived RS256 JWT proving this request comes from a
    legitimately-licensed opama instance. Sent as `Authorization: Bearer
    <token>` to a plugin's download_url — symmetric to the X-Opama-Plugin-Token
    proxy pattern, but a distinct claim shape (documented alongside it in
    plugin_signing.py).

    Claims: {iss, instance_id, plugin_id, tier, iat, exp}. Deliberately
    excludes LicenseInfo.customer — disclosing the licensee's identity to a
    third-party vendor on every install is a privacy decision the
    self-hoster should opt into explicitly, not get by default.
    `instance_id` + `tier` is sufficient for a vendor to gate by tier.

    No nonce / replay protection — would be inconsistent over-engineering
    relative to the existing proxy token's accepted risk tolerance.
    """
    return _sign({"plugin_id": plugin_id, "tier": tier}, ttl_seconds=ttl_seconds)


# ---------------------------------------------------------------------------
# Manifest validation
# ---------------------------------------------------------------------------

def validate_local_manifest(data: dict, plugin_id: str) -> None:
    """Raise 422 if `data` (a parsed plugin.yaml) is unfit for a local install."""
    missing = [f for f in ("download_url", "router_module") if not data.get(f)]
    if missing:
        raise HTTPException(422, detail=f"Local plugin manifest missing required fields: {missing}")

    if data.get("model_modules"):
        raise HTTPException(
            422,
            detail=(
                "Local plugin installs cannot declare model_modules in v1 — "
                "dynamically-installed plugins must be schema-free (introduce "
                "no new DB tables). See app/plugin_installer.py module "
                "docstring for why."
            ),
        )

    manifest_id = (data.get("id") or "").strip()
    if manifest_id and manifest_id != plugin_id:
        raise HTTPException(
            422,
            detail=f"Manifest id '{manifest_id}' does not match requested plugin_id '{plugin_id}'",
        )

    router_attr = data.get("router_attr", "router")
    if router_attr != "router":
        raise HTTPException(
            422,
            detail=(
                "Local plugin manifests must expose their APIRouter as "
                "'router' — router_attr overrides are not supported for "
                "dynamically-installed plugins in v1"
            ),
        )


# ---------------------------------------------------------------------------
# Safe download + extraction pipeline
# ---------------------------------------------------------------------------

def download_and_extract(
    plugin_id: str,
    version: str,
    download_url: str,
    token: str,
    dest_root: Path = DYNAMIC_PLUGINS_ROOT,
) -> tuple[Path, dict]:
    """
    Download `download_url` (bearer-authenticated with `token`), safely
    extract it, and atomically place it at `<dest_root>/<plugin_id>-<version>/`.

    Returns (final_install_path, parsed_plugin_yaml_dict).

    Pipeline (see module docstring "Security model" for the full rationale):
      1. SSRF guard on download_url.
      2. Stream-download to a capped temp file *inside dest_root* — same
         filesystem, so the final placement can be an atomic os.rename().
      3. Sniff the archive format (tarfile.is_tarfile / zipfile.is_zipfile —
         never trust the URL's extension).
      4. Extract member-by-member into a fresh temp dir (also inside
         dest_root) applying the full safe-extraction guard set.
      5. Detect & strip a single common wrapper directory (GitHub-tarball
         convention) so install_path points at the actual package.
      6. Parse the extracted plugin.yaml and validate its `id` matches
         plugin_id (stops a malicious archive claiming to be a
         different/higher-trust plugin).
      7. os.rename() into its final versioned location — only on full
         success. No partially-extracted directory is ever visible to the
         loader; version-suffixing means an in-place update lands alongside
         the running version rather than over it.
    """
    try:
        assert_public_url(download_url, "Plugin download URL")
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    dest_root.mkdir(parents=True, exist_ok=True)
    final_path = dest_root / f"{plugin_id}-{version}"

    archive_path: Path | None = None
    extract_dir: Path | None = None
    try:
        archive_path = _stream_download(download_url, token, dest_root)
        extract_dir = _safe_extract(archive_path, dest_root)
        package_dir = _strip_wrapper_dir(extract_dir)
        manifest = _load_and_validate_extracted_manifest(package_dir, plugin_id)

        if final_path.exists():
            shutil.rmtree(final_path)
        os.rename(package_dir, final_path)
        return final_path, manifest
    finally:
        if archive_path is not None:
            archive_path.unlink(missing_ok=True)
        if extract_dir is not None and extract_dir.exists() and extract_dir != final_path:
            shutil.rmtree(extract_dir, ignore_errors=True)


def _stream_download(download_url: str, token: str, dest_root: Path) -> Path:
    """Stream `download_url` to a size-capped temp file inside `dest_root`."""
    fd, raw_path = tempfile.mkstemp(prefix=".plugin-download-", suffix=".bin", dir=dest_root)
    archive_path = Path(raw_path)
    headers = {"Authorization": f"Bearer {token}"}
    written = 0
    try:
        with os.fdopen(fd, "wb") as fh:
            with httpx.stream("GET", download_url, headers=headers, timeout=60.0, follow_redirects=True) as resp:
                resp.raise_for_status()
                for chunk in resp.iter_bytes():
                    written += len(chunk)
                    if written > MAX_DOWNLOAD_BYTES:
                        raise HTTPException(
                            422,
                            detail=f"Plugin archive exceeds the {MAX_DOWNLOAD_BYTES // (1024 * 1024)} MB download limit",
                        )
                    fh.write(chunk)
    except httpx.HTTPError as exc:
        archive_path.unlink(missing_ok=True)
        raise HTTPException(502, detail=f"Could not download plugin archive: {exc}")
    except BaseException:
        archive_path.unlink(missing_ok=True)
        raise
    return archive_path


def _safe_extract(archive_path: Path, dest_root: Path) -> Path:
    """
    Sniff `archive_path`'s format and extract it member-by-member into a
    fresh temp directory inside `dest_root`. Returns the extraction directory.
    """
    extract_dir = Path(tempfile.mkdtemp(prefix=".plugin-extract-", dir=dest_root))
    try:
        if tarfile.is_tarfile(archive_path):
            _extract_tar(archive_path, extract_dir)
        elif zipfile.is_zipfile(archive_path):
            _extract_zip(archive_path, extract_dir)
        else:
            raise HTTPException(422, detail="Plugin archive is neither a valid tar nor zip file")
    except ValueError as exc:
        # _safe_member_dest / member-type checks raise plain ValueError so
        # they stay independently unit-testable; surface as a 422 here.
        shutil.rmtree(extract_dir, ignore_errors=True)
        raise HTTPException(422, detail=str(exc))
    except BaseException:
        shutil.rmtree(extract_dir, ignore_errors=True)
        raise
    return extract_dir


def _safe_member_dest(name: str, dest_root: Path) -> Path:
    """
    Resolve an archive member's name to a safe destination inside `dest_root`,
    raising ValueError on anything that could escape it.

    Resolve-then-compare — never string-prefix-check, which is bypassable via
    sibling-directory names (e.g. a member named "../dest_root_evil/x").
    """
    if not name or "\0" in name or Path(name).is_absolute():
        raise ValueError(f"unsafe path in archive: {name!r}")
    target = (dest_root / name).resolve()
    root = dest_root.resolve()
    if target != root and not target.is_relative_to(root):
        raise ValueError(f"path traversal in archive: {name!r}")
    return target


def _extract_tar(archive_path: Path, extract_dir: Path) -> None:
    with tarfile.open(archive_path) as tar:
        members = tar.getmembers()
        if len(members) > MAX_MEMBERS:
            raise ValueError(f"plugin archive has too many entries (> {MAX_MEMBERS})")

        total = 0
        for member in members:
            if member.issym() or member.islnk() or member.isdev():
                raise ValueError(f"unsafe member type in archive: {member.name!r}")

            target = _safe_member_dest(member.name, extract_dir)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                continue

            total += member.size
            if total > MAX_EXTRACTED_BYTES:
                raise ValueError(f"plugin archive exceeds the {MAX_EXTRACTED_BYTES // (1024 * 1024)} MB extracted-size limit")

            target.parent.mkdir(parents=True, exist_ok=True)
            src = tar.extractfile(member)
            if src is None:
                continue
            with open(target, "wb") as out:
                shutil.copyfileobj(src, out)
            os.chmod(target, _EXTRACTED_FILE_MODE)


def _extract_zip(archive_path: Path, extract_dir: Path) -> None:
    with zipfile.ZipFile(archive_path) as zf:
        infos = zf.infolist()
        if len(infos) > MAX_MEMBERS:
            raise ValueError(f"plugin archive has too many entries (> {MAX_MEMBERS})")

        total = 0
        for info in infos:
            # The Unix mode lives in the top 16 bits of external_attr.
            unix_mode = info.external_attr >> 16
            if stat.S_ISLNK(unix_mode):
                raise ValueError(f"unsafe member type in archive: {info.filename!r}")

            target = _safe_member_dest(info.filename, extract_dir)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue

            total += info.file_size
            if total > MAX_EXTRACTED_BYTES:
                raise ValueError(f"plugin archive exceeds the {MAX_EXTRACTED_BYTES // (1024 * 1024)} MB extracted-size limit")

            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
            os.chmod(target, _EXTRACTED_FILE_MODE)


def _strip_wrapper_dir(extract_dir: Path) -> Path:
    """
    GitHub tarballs wrap their contents in a single "reponame-sha/" directory.
    If `extract_dir` contains exactly one entry and it's a directory, treat
    that as the package root; otherwise the archive root *is* the package.
    """
    entries = list(extract_dir.iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return extract_dir


def _load_and_validate_extracted_manifest(package_dir: Path, plugin_id: str) -> dict:
    manifest_path = package_dir / "plugin.yaml"
    if not manifest_path.is_file():
        raise HTTPException(422, detail="Downloaded archive does not contain a plugin.yaml at its package root")

    try:
        data = yaml.safe_load(manifest_path.read_text())
    except Exception as exc:
        raise HTTPException(422, detail=f"Downloaded plugin.yaml is not valid YAML: {exc}")
    if not isinstance(data, dict):
        raise HTTPException(422, detail="Downloaded plugin.yaml must be a mapping")

    manifest_id = (data.get("id") or "").strip()
    if manifest_id != plugin_id:
        raise HTTPException(
            422,
            detail=(
                f"Downloaded archive's plugin.yaml declares id '{manifest_id}', "
                f"expected '{plugin_id}' — refusing to install a possibly-spoofed package"
            ),
        )
    return data


# ---------------------------------------------------------------------------
# Garbage collection — sweeps installs no longer referenced by an enabled row
# ---------------------------------------------------------------------------

def _gc_orphaned_local_installs(session, dynamic_plugins_root: Path = DYNAMIC_PLUGINS_ROOT) -> None:
    """
    Remove any directory directly under `dynamic_plugins_root` that isn't the
    install_path of a currently-enabled type=local DynamicPlugin row.

    One mechanism handles both uninstall cleanup (row deleted/disabled) and
    orphaned-old-version cleanup after an update (row repointed to a new
    versioned dir) — see plan decision 5. Called once at startup, *after*
    load_dynamic_plugins()'s load loop, so a directory is never removed while
    its module might still be imported and its router still mounted in the
    running process (that risk is exactly why uninstall doesn't rmtree
    immediately).
    """
    if not dynamic_plugins_root.is_dir():
        return

    from sqlmodel import select
    from services.plugin_store.models import DynamicPlugin

    rows = session.exec(
        select(DynamicPlugin).where(
            DynamicPlugin.type == "local",
            DynamicPlugin.enabled == True,  # noqa: E712
        )
    ).all()
    active_paths = {Path(r.install_path).resolve() for r in rows if r.install_path}

    for entry in dynamic_plugins_root.iterdir():
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        if entry.resolve() in active_paths:
            continue
        logger.info("🧹 Removed orphaned plugin install: %s", entry)
        shutil.rmtree(entry, ignore_errors=True)
