"""
Storefront API router — mounted at /storefront.

Manages items a user lists for sale on an external static shop site. Owns
shop settings, listing/sales views, and the publish flow. Publishing builds
a `catalog.json` from the user's listed assets and pushes it to the first
configured target that succeeds: GitHub Contents API (via the github_publish
module) → filesystem path → webhook. See `_build_catalog()` and `publish()`
below, and the Storefront section of CLAUDE.md for the end-to-end
sale-writeback flow.
"""
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
from services.auth.org_context import OrgContext
from services.auth.entitlements import require_tier
from services.custom_assets.models import CustomAsset, CustomAssetField
from services.custom_assets.router import _category_slug
from services.github_publish.client import get_publish_config, commit_file

from app.network_validators import assert_public_url
from .models import StorefrontSettings
from .schemas import (
    StorefrontSettingsIn,
    StorefrontSettingsOut,
    StorefrontListingPatch,
    PublishResult,
    ImageUrlTestRequest,
    ImageUrlTestResult,
)

router = APIRouter(prefix="/storefront", tags=["storefront"])

# Storefront is a premium-tier plugin (plugin.yaml). Gates org-scoped endpoints
# on the active org's plan when ENTITLEMENT_MODE=org; pass-through (resolves the
# active org like get_current_org) in the default "license" mode.
require_storefront = require_tier("premium", module="storefront")

_PUBLIC_API_URL = os.environ.get("PUBLIC_API_URL", "").rstrip("/")


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


def _get_settings(org_id: int, session: Session) -> Optional[StorefrontSettings]:
    return session.exec(
        select(StorefrontSettings).where(StorefrontSettings.org_id == org_id)
    ).first()


def _settings_out(s: StorefrontSettings) -> StorefrontSettingsOut:
    return StorefrontSettingsOut(
        id=s.id,
        user_id=s.user_id,
        site_name=s.site_name,
        site_url=s.site_url,
        public_api_url=s.public_api_url,
        catalog_path=s.catalog_path,
        webhook_url=s.webhook_url,
        last_published_at=s.last_published_at,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


# ── Settings ──────────────────────────────────────────────────────────────────

@router.get("/settings", response_model=StorefrontSettingsOut)
def get_settings(
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(require_storefront),
):
    s = _get_settings(ctx.org_id, session)
    if not s:
        raise HTTPException(404, "Storefront not configured yet")
    return _settings_out(s)


@router.put("/settings", response_model=StorefrontSettingsOut)
def upsert_settings(
    body: StorefrontSettingsIn,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    ctx: OrgContext = Depends(require_storefront),
):
    s = _get_settings(ctx.org_id, session)
    data = body.model_dump()

    # SSRF protection: validate webhook_url before saving
    if data.get("webhook_url"):
        try:
            assert_public_url(data["webhook_url"], "Webhook URL")
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    is_new = s is None
    if s:
        for field, val in data.items():
            setattr(s, field, val)
        s.updated_at = datetime.utcnow().isoformat()
    else:
        # org_id = owning organization (tenancy scope); user_id = creator (audit)
        s = StorefrontSettings(org_id=ctx.org_id, user_id=current_user.id, **data)

    session.add(s)
    session.commit()
    session.refresh(s)

    detail = "created settings" if is_new else "updated settings"
    write_audit_log(
        session,
        action="storefront.settings_update",
        user=current_user,
        target=f"user:{current_user.id}",
        request=request,
        detail=detail,
    )

    return _settings_out(s)


@router.post("/settings/test-image-url", response_model=ImageUrlTestResult)
def test_image_url(
    body: ImageUrlTestRequest,
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(require_storefront),
):
    """Check that `public_api_url` is reachable and serves an item image.

    Picks one of the org's listed assets that has an image and fetches it
    through the candidate public URL — the same path the storefront site
    will use. Falls back to `/healthz` if the org has no item images yet.
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
            CustomAsset.org_id == ctx.org_id,
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
    ctx: OrgContext = Depends(require_storefront),
):
    assets = session.exec(
        select(CustomAsset).where(
            CustomAsset.org_id == ctx.org_id,
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
    ctx: OrgContext = Depends(require_storefront),
):
    asset = session.get(CustomAsset, asset_id)
    if not asset:
        raise HTTPException(404, "Asset not found")
    if asset.org_id != ctx.org_id:
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
    ctx: OrgContext = Depends(require_storefront),
):
    sold = session.exec(
        select(CustomAsset).where(
            CustomAsset.org_id == ctx.org_id,
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
    ctx: OrgContext = Depends(require_storefront),
):
    s = _get_settings(ctx.org_id, session)
    public_base = s.public_api_url if s else ""
    catalog, sold_count = _generate_catalog(ctx.org_id, session, public_base)
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
    ctx: OrgContext = Depends(require_storefront),
):
    """Build the catalog and push it to the first configured target that works.

    The three targets are a fallback chain, NOT a broadcast: each is attempted
    only if the previous didn't succeed (`if not published`). So a user with
    GitHub configured publishes only via GitHub; the file path and webhook are
    there for local dev or non-GitHub setups. `error_msg` holds the failure
    from the last target tried when none succeed.
    """
    s = _get_settings(ctx.org_id, session)
    public_base = s.public_api_url if s else ""
    catalog, sold_count = _generate_catalog(ctx.org_id, session, public_base)
    catalog_json = json.dumps(catalog, indent=2, ensure_ascii=False)

    published = False
    error_msg: Optional[str] = None
    github_commit_url: Optional[str] = None

    # ── 1. GitHub (commits catalog.json → triggers Cloudflare auto-deploy) ──
    gh_config = get_publish_config(session, current_user.id)
    if gh_config:
        commit_msg = gh_config.commit_message.replace("{n}", str(len(catalog)))
        ok, commit_url, gh_error = commit_file(
            token=gh_config.token, repo=gh_config.repo,
            file_path=gh_config.file_path, content=catalog_json,
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
    org_id: int,
    session: Session,
    public_base: str,
) -> tuple[list[dict], int]:
    assets = session.exec(
        select(CustomAsset).where(
            CustomAsset.org_id == org_id,
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
