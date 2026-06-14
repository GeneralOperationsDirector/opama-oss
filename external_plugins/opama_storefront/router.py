"""
Storefront API router — mounted at /storefront.

Manages items a user lists for sale on an external static shop site. Owns
shop settings (including a GitHub token that is stored encrypted and never
returned — only a hint), listing/sales views, and the publish flow. Publishing
builds a `catalog.json` from the user's listed assets and pushes it to the
first configured target that succeeds: GitHub Contents API → filesystem path →
webhook. See `_build_catalog()` and `publish()` below, and the Storefront
section of CLAUDE.md for the end-to-end sale-writeback flow.
"""
import base64
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select

from services.shared.audit import write_audit_log
from services.shared.database import get_session
from services.shared.models import User
from services.auth.middleware import get_current_user
from services.custom_assets.models import CustomAsset, CustomAssetField
from services.custom_assets.router import _category_slug

from app.secrets import encrypt_secret, decrypt_secret_safe, secret_hint
from app.network_validators import assert_public_url
from .models import StorefrontSettings
from .schemas import (
    StorefrontSettingsIn,
    StorefrontSettingsOut,
    StorefrontListingPatch,
    PublishResult,
    GitHubTestRequest,
    GitHubTestResult,
    ImageUrlTestRequest,
    ImageUrlTestResult,
)

router = APIRouter(prefix="/storefront", tags=["storefront"])

_PUBLIC_API_URL = os.environ.get("PUBLIC_API_URL", "").rstrip("/")
_GITHUB_API = "https://api.github.com"


# ── helpers ──────────────────────────────────────────────────────────────────

def _resolve_image(url: Optional[str], public_base: str) -> Optional[str]:
    """Turn a stored image path into an absolute URL the shop can load.

    Uploads are stored as site-relative paths (`/uploads/assets/5.jpg`). The
    external storefront runs on a different origin, so those must be prefixed
    with a publicly reachable base — the user's `public_api_url`, falling back
    to the `PUBLIC_API_URL` env var. Already-absolute URLs are passed through.
    """
    if not url:
        return None
    if url.startswith("http"):
        return url
    base = public_base.rstrip("/") or _PUBLIC_API_URL
    return f"{base}{url}" if base else url


def _build_catalog_entry(
    asset: CustomAsset,
    fields: list[CustomAssetField],
    public_base: str = "",
) -> dict:
    """Map one CustomAsset to the storefront `catalog.json` entry schema.

    Keys are camelCase because they're consumed directly by the static shop
    site's JS. Notes on the non-obvious fields:
    - `id` uses the user-set `website_slug` when present (stable, human-readable
      URLs) and falls back to the numeric asset id.
    - `sold` is derived from `sale_date` being set — the shop greys out sold
      items rather than removing them.
    - `marketplaceLinks` prefers the dedicated `marketplace_*` columns but
      falls back to same-named custom fields for older items.
    """
    field_map = {f.key: f.value for f in fields}
    images = [
        u for u in [
            _resolve_image(asset.image_url, public_base),
            _resolve_image(asset.back_image_url, public_base),
        ] if u
    ]
    mp_keys = ("ebay", "facebook", "kijiji", "craigslist")
    return {
        "id": asset.website_slug or str(asset.id),
        "title": asset.name,
        "category": _category_slug(asset.category),
        "condition": asset.condition or "",
        "description": asset.description or "",
        "priceCad": asset.listing_price_cad or 0.0,
        "shippingCad": asset.shipping_price_cad or 0.0,
        "images": images,
        "sold": bool(asset.sale_date),
        "marketplaceLinks": {
            k: (getattr(asset, f"marketplace_{k}", None) or field_map.get(k, "")) or ""
            for k in mp_keys
        },
    }


def _get_settings(user_id: int, session: Session) -> Optional[StorefrontSettings]:
    return session.exec(
        select(StorefrontSettings).where(StorefrontSettings.user_id == user_id)
    ).first()


def _settings_out(s: StorefrontSettings) -> StorefrontSettingsOut:
    token = s.github_token
    # Decrypt to get the plaintext only for the hint; never return plaintext itself
    plaintext_hint: Optional[str] = None
    if token:
        try:
            plain = decrypt_secret_safe(token)
            plaintext_hint = secret_hint(plain)
        except Exception:
            plaintext_hint = "…????"
    return StorefrontSettingsOut(
        id=s.id,
        user_id=s.user_id,
        site_name=s.site_name,
        site_url=s.site_url,
        public_api_url=s.public_api_url,
        catalog_path=s.catalog_path,
        webhook_url=s.webhook_url,
        github_token_set=bool(token),
        github_token_hint=plaintext_hint,
        github_repo=s.github_repo,
        github_file_path=s.github_file_path,
        github_commit_message=s.github_commit_message,
        last_published_at=s.last_published_at,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


def _github_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _github_commit(
    token: str,
    repo: str,
    file_path: str,
    content: str,
    commit_message: str,
) -> tuple[bool, Optional[str], Optional[str]]:
    """
    Commit content to a file in a GitHub repo via the Contents API.
    Returns (success, commit_html_url, error_message).
    """
    url = f"{_GITHUB_API}/repos/{repo}/contents/{file_path}"
    headers = _github_headers(token)

    # Fetch current SHA (required to update an existing file)
    sha: Optional[str] = None
    get_resp = httpx.get(url, headers=headers, timeout=15)
    if get_resp.status_code == 200:
        sha = get_resp.json().get("sha")
    elif get_resp.status_code == 404:
        pass  # File doesn't exist yet — create it
    else:
        return False, None, f"GitHub GET failed: {get_resp.status_code} {get_resp.text[:200]}"

    body: dict = {
        "message": commit_message,
        "content": base64.b64encode(content.encode()).decode(),
    }
    if sha:
        body["sha"] = sha

    put_resp = httpx.put(url, headers=headers, json=body, timeout=15)
    if put_resp.status_code in (200, 201):
        commit_url = put_resp.json().get("commit", {}).get("html_url")
        return True, commit_url, None
    else:
        return False, None, f"GitHub PUT failed: {put_resp.status_code} {put_resp.text[:300]}"


# ── Settings ──────────────────────────────────────────────────────────────────

@router.get("/settings", response_model=StorefrontSettingsOut)
def get_settings(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    s = _get_settings(current_user.id, session)
    if not s:
        raise HTTPException(404, "Storefront not configured yet")
    return _settings_out(s)


@router.put("/settings", response_model=StorefrontSettingsOut)
def upsert_settings(
    body: StorefrontSettingsIn,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    s = _get_settings(current_user.id, session)
    data = body.model_dump()

    # SSRF protection: validate webhook_url before saving
    if data.get("webhook_url"):
        try:
            assert_public_url(data["webhook_url"], "Webhook URL")
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    # Encrypt the GitHub token if a new one was supplied
    new_token = data.get("github_token")
    token_changed = bool(new_token)
    if new_token:
        data["github_token"] = encrypt_secret(new_token)
    elif s and s.github_token:
        # Blank field = preserve existing encrypted token
        data["github_token"] = s.github_token

    is_new = s is None
    if s:
        for field, val in data.items():
            setattr(s, field, val)
        s.updated_at = datetime.utcnow().isoformat()
    else:
        s = StorefrontSettings(user_id=current_user.id, **data)

    session.add(s)
    session.commit()
    session.refresh(s)

    detail = "created settings" if is_new else "updated settings"
    if token_changed:
        detail += "; github_token changed"
    write_audit_log(
        session,
        action="storefront.settings_update",
        user=current_user,
        target=f"user:{current_user.id}",
        request=request,
        detail=detail,
    )

    return _settings_out(s)


@router.post("/settings/test-github", response_model=GitHubTestResult)
def test_github(
    body: GitHubTestRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Verify a GitHub token can read/write the configured repo via GET /repos/{repo}.

    Accepts an unsaved token/repo from the form so the button works before
    the user clicks Save, falling back to the stored settings otherwise.
    """
    s = _get_settings(current_user.id, session)
    repo = body.github_repo or (s.github_repo if s else None)
    if body.github_token:
        token = body.github_token
    elif s and s.github_token:
        token = decrypt_secret_safe(s.github_token)
    else:
        token = None

    if not repo or not token:
        raise HTTPException(422, "GitHub token and repository are required")

    resp = httpx.get(f"{_GITHUB_API}/repos/{repo}", headers=_github_headers(token), timeout=15)
    if resp.status_code == 200:
        data = resp.json()
        return GitHubTestResult(
            connected=True,
            repo_full_name=data.get("full_name"),
            private=data.get("private"),
            can_push=data.get("permissions", {}).get("push", False),
        )
    if resp.status_code == 401:
        return GitHubTestResult(connected=False, error="GitHub token is invalid or expired")
    if resp.status_code == 404:
        return GitHubTestResult(connected=False, error=f"Repository '{repo}' not found, or the token lacks access to it")
    return GitHubTestResult(connected=False, error=f"GitHub API error: {resp.status_code}")


@router.post("/settings/test-image-url", response_model=ImageUrlTestResult)
def test_image_url(
    body: ImageUrlTestRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Check that `public_api_url` is reachable and serves an item image.

    Picks one of the user's listed assets that has an image and fetches it
    through the candidate public URL — the same path the storefront site
    will use. Falls back to `/healthz` if the user has no item images yet.
    """
    base = body.public_api_url.rstrip("/")
    if not base:
        raise HTTPException(422, "Public API URL is required")

    try:
        assert_public_url(base, "Public API URL")
    except ValueError as exc:
        return ImageUrlTestResult(reachable=False, tested_url=base, error=str(exc))

    asset = session.exec(
        select(CustomAsset).where(
            CustomAsset.user_id == current_user.id,
            CustomAsset.image_url.is_not(None),
        )
    ).first()
    tested_url = f"{base}{asset.image_url}" if asset and asset.image_url else f"{base}/healthz"

    try:
        resp = httpx.get(tested_url, timeout=10, follow_redirects=True)
    except httpx.HTTPError as exc:
        return ImageUrlTestResult(reachable=False, tested_url=tested_url, error=str(exc))

    content_type = resp.headers.get("content-type")
    if resp.status_code != 200:
        return ImageUrlTestResult(reachable=False, tested_url=tested_url, status_code=resp.status_code, content_type=content_type, error=f"HTTP {resp.status_code}")
    return ImageUrlTestResult(reachable=True, tested_url=tested_url, status_code=resp.status_code, content_type=content_type)


# ── Listings ──────────────────────────────────────────────────────────────────

@router.get("/listings")
def get_listings(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    assets = session.exec(
        select(CustomAsset).where(
            CustomAsset.user_id == current_user.id,
            CustomAsset.listed_on_website == True,  # noqa: E712
        ).order_by(CustomAsset.updated_at.desc())
    ).all()
    result = []
    for a in assets:
        fields = session.exec(
            select(CustomAssetField).where(CustomAssetField.asset_id == a.id)
        ).all()
        d = a.model_dump()
        d["_catalog_preview"] = _build_catalog_entry(a, fields)
        result.append(d)
    return result


@router.patch("/listings/{asset_id}")
def patch_listing(
    asset_id: int,
    body: StorefrontListingPatch,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    asset = session.get(CustomAsset, asset_id)
    if not asset:
        raise HTTPException(404, "Asset not found")
    if asset.user_id != current_user.id:
        raise HTTPException(403, "Forbidden")
    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(asset, field, val)
    asset.updated_at = datetime.utcnow().isoformat()
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset


# ── Sales ─────────────────────────────────────────────────────────────────────

@router.get("/sales")
def get_sales(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    sold = session.exec(
        select(CustomAsset).where(
            CustomAsset.user_id == current_user.id,
            CustomAsset.sale_date != None,  # noqa: E711
        ).order_by(CustomAsset.sale_date.desc())
    ).all()

    total_revenue = sum(a.sale_price_cad or 0 for a in sold)
    by_platform: dict[str, float] = {}
    for a in sold:
        plat = a.sale_platform or "unknown"
        by_platform[plat] = by_platform.get(plat, 0) + (a.sale_price_cad or 0)

    return {
        "total_revenue_cad": round(total_revenue, 2),
        "total_sold": len(sold),
        "by_platform": by_platform,
        "items": [a.model_dump() for a in sold],
    }


# ── Publish ───────────────────────────────────────────────────────────────────

@router.get("/publish/preview")
def preview_catalog(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    s = _get_settings(current_user.id, session)
    public_base = s.public_api_url if s else ""
    catalog, sold_count = _generate_catalog(current_user.id, session, public_base)
    return {
        "item_count": len(catalog),
        "sold_count": sold_count,
        "catalog": catalog,
    }


@router.post("/publish", response_model=PublishResult)
def publish_catalog(
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Build the catalog and push it to the first configured target that works.

    The three targets are a fallback chain, NOT a broadcast: each is attempted
    only if the previous didn't succeed (`if not published`). So a user with
    GitHub configured publishes only via GitHub; the file path and webhook are
    there for local dev or non-GitHub setups. `error_msg` holds the failure
    from the last target tried when none succeed.
    """
    s = _get_settings(current_user.id, session)
    public_base = s.public_api_url if s else ""
    catalog, sold_count = _generate_catalog(current_user.id, session, public_base)
    catalog_json = json.dumps(catalog, indent=2, ensure_ascii=False)

    published = False
    error_msg: Optional[str] = None
    github_commit_url: Optional[str] = None

    # ── 1. GitHub (commits catalog.json → triggers Cloudflare auto-deploy) ──
    if s and s.github_token and s.github_repo and s.github_file_path:
        commit_msg = (
            s.github_commit_message or "chore: publish catalog ({n} items)"
        ).replace("{n}", str(len(catalog)))

        ok, commit_url, gh_error = _github_commit(
            token=decrypt_secret_safe(s.github_token),
            repo=s.github_repo,
            file_path=s.github_file_path,
            content=catalog_json,
            commit_message=commit_msg,
        )
        if ok:
            published = True
            github_commit_url = commit_url
        else:
            error_msg = gh_error

    # ── 2. Local file path (fallback / local dev) ─────────────────────────────
    if not published and s and s.catalog_path:
        try:
            path = Path(s.catalog_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(catalog_json)
            published = True
        except Exception as exc:
            error_msg = f"File write failed: {exc}"

    # ── 3. Webhook URL (generic HTTP target) ──────────────────────────────────
    if not published and s and s.webhook_url:
        try:
            resp = httpx.post(
                s.webhook_url,
                content=catalog_json,
                headers={"Content-Type": "application/json"},
                timeout=15,
            )
            resp.raise_for_status()
            published = True
        except Exception as exc:
            error_msg = f"Webhook failed: {exc}"

    # ── Update last_published_at on any success ───────────────────────────────
    last_pub = None
    if published and s:
        s.last_published_at = datetime.utcnow().isoformat()
        s.updated_at = datetime.utcnow().isoformat()
        session.add(s)
        session.commit()
        last_pub = s.last_published_at

    write_audit_log(
        session,
        action="storefront.publish",
        user=current_user,
        target=f"user:{current_user.id}",
        request=request,
        success=published,
        detail=(
            f"published {len(catalog)} items ({sold_count} sold)"
            + (f" → {github_commit_url}" if github_commit_url else "")
            if published
            else f"publish failed: {error_msg}"
        ),
    )

    return PublishResult(
        published=published,
        item_count=len(catalog),
        sold_count=sold_count,
        last_published_at=last_pub,
        error=error_msg,
        catalog=catalog,
        github_commit_url=github_commit_url,
    )


# Also imported by external_plugins/opama_shopify/router.py (its own repo,
# opama-oss-shopify) to build the product list it syncs to Shopify — keep its
# signature/return shape stable, or update that plugin in lockstep. See
# external_plugins/opama_shopify/README.md "Dependencies".
def _generate_catalog(
    user_id: int,
    session: Session,
    public_base: str,
) -> tuple[list[dict], int]:
    assets = session.exec(
        select(CustomAsset).where(
            CustomAsset.user_id == user_id,
            CustomAsset.listed_on_website == True,  # noqa: E712
        )
    ).all()
    catalog = []
    sold_count = 0
    for a in assets:
        fields = session.exec(
            select(CustomAssetField).where(CustomAssetField.asset_id == a.id)
        ).all()
        entry = _build_catalog_entry(a, fields, public_base)
        catalog.append(entry)
        if entry["sold"]:
            sold_count += 1
    return catalog, sold_count
