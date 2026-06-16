"""
Shopify storefront-publish plugin — mounted at /shopify.

Pushes the opama storefront catalog (CustomAsset listings with
listed_on_website=true) to a merchant's Shopify store as products via the
Admin REST API. Sibling publish target to GitHub/file/webhook in
external_plugins/opama_storefront/router.py — reuses `_generate_catalog()`
so catalog.json and the Shopify store stay in sync. See
external_plugins/README.md for the external-plugin loading mechanism.
"""

import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select

from services.shared.audit import write_audit_log
from services.shared.database import get_session
from services.shared.models import User
from services.auth.middleware import get_current_user
from opama_storefront.models import StorefrontSettings
from opama_storefront.router import _generate_catalog

from app.secrets import encrypt_secret, decrypt_secret_safe, secret_hint

from .client import ShopifyClient, ShopifyAPIError
from .models import ShopifySettings, ShopifyProductMapping
from .schemas import ShopifySettingsIn, ShopifySettingsOut, ShopifyPublishResult

router = APIRouter(prefix="/shopify", tags=["shopify"])

# Admin API access tokens are scoped to a single *.myshopify.com store —
# restricting to this suffix keeps ShopifyClient from being pointed at an
# arbitrary host (defense-in-depth alongside the token itself).
_SHOP_DOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*\.myshopify\.com$")


# ── helpers ──────────────────────────────────────────────────────────────────

def _get_settings(user_id: int, session: Session) -> Optional[ShopifySettings]:
    return session.exec(
        select(ShopifySettings).where(ShopifySettings.user_id == user_id)
    ).first()


def _settings_out(s: ShopifySettings) -> ShopifySettingsOut:
    token = s.access_token
    hint: Optional[str] = None
    if token:
        try:
            hint = secret_hint(decrypt_secret_safe(token))
        except Exception:
            hint = "…????"
    return ShopifySettingsOut(
        id=s.id,
        user_id=s.user_id,
        shop_domain=s.shop_domain,
        access_token_set=bool(token),
        access_token_hint=hint,
        last_published_at=s.last_published_at,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


def _catalog_for_publish(user_id: int, session: Session) -> tuple[list[dict], int]:
    """Build the storefront catalog using the user's public_api_url (if any)
    so image URLs are absolute — Shopify fetches `images[].src` itself."""
    storefront_settings = session.exec(
        select(StorefrontSettings).where(StorefrontSettings.user_id == user_id)
    ).first()
    public_base = storefront_settings.public_api_url if storefront_settings else ""
    return _generate_catalog(user_id, session, public_base)


def _build_shopify_product(entry: dict) -> dict:
    """Map one storefront catalog entry to a Shopify product payload."""
    return {
        "title": entry["title"],
        "body_html": entry["description"],
        "vendor": "opama",
        "product_type": entry["category"],
        "tags": entry["condition"],
        "status": "active",
        # Shopify fetches images by URL — relative /uploads/... paths are
        # useless to it, so only forward already-absolute URLs.
        "images": [{"src": url} for url in entry["images"] if url.startswith("http")],
        "variants": [{
            "price": f"{entry['priceCad']:.2f}",
            "sku": entry["id"],
            "inventory_management": None,
        }],
    }


# ── Settings ──────────────────────────────────────────────────────────────────

@router.get("/settings", response_model=ShopifySettingsOut)
def get_settings(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    s = _get_settings(current_user.id, session)
    if not s:
        raise HTTPException(404, "Shopify not configured yet")
    return _settings_out(s)


@router.put("/settings", response_model=ShopifySettingsOut)
def upsert_settings(
    body: ShopifySettingsIn,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    s = _get_settings(current_user.id, session)
    data = body.model_dump()

    if data["shop_domain"] and not _SHOP_DOMAIN_RE.match(data["shop_domain"]):
        raise HTTPException(422, "shop_domain must be a *.myshopify.com domain")

    new_token = data.pop("access_token", None)
    token_changed = bool(new_token)
    if new_token:
        data["access_token"] = encrypt_secret(new_token)
    elif s and s.access_token:
        data["access_token"] = s.access_token  # blank = preserve existing

    is_new = s is None
    if s:
        for field, val in data.items():
            setattr(s, field, val)
        s.updated_at = datetime.utcnow().isoformat()
    else:
        s = ShopifySettings(user_id=current_user.id, **data)

    session.add(s)
    session.commit()
    session.refresh(s)

    detail = "created settings" if is_new else "updated settings"
    if token_changed:
        detail += "; access_token changed"
    write_audit_log(
        session,
        action="shopify.settings_update",
        user=current_user,
        target=f"user:{current_user.id}",
        request=request,
        detail=detail,
    )

    return _settings_out(s)


@router.post("/settings/test")
def test_connection(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Verify the configured shop_domain/access_token via GET /shop.json."""
    s = _get_settings(current_user.id, session)
    if not s or not s.shop_domain or not s.access_token:
        raise HTTPException(422, "Shopify is not configured yet")
    client = ShopifyClient(s.shop_domain, decrypt_secret_safe(s.access_token))
    try:
        shop = client.get_shop()
    except ShopifyAPIError as exc:
        raise HTTPException(502, f"Shopify connection failed: {exc}")
    return {"connected": True, "shop_name": shop.get("name"), "domain": shop.get("domain")}


# ── Publish ───────────────────────────────────────────────────────────────────

@router.get("/publish/preview")
def preview_publish(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Preview the Shopify product payloads /shopify/publish would send,
    without contacting Shopify. Sold items are skipped — Shopify has no
    direct equivalent of catalog.json's `sold` flag in this v1."""
    catalog, sold_count = _catalog_for_publish(current_user.id, session)
    products = [_build_shopify_product(e) for e in catalog if not e["sold"]]
    return {
        "item_count": len(products),
        "skipped_sold_count": sold_count,
        "products": products,
    }


@router.post("/publish", response_model=ShopifyPublishResult)
def publish_to_shopify(
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Create or update a Shopify product for every active (unsold) listing.

    `ShopifyProductMapping` rows remember each catalog entry's Shopify
    product id so re-publishing updates the existing product instead of
    creating duplicates.
    """
    s = _get_settings(current_user.id, session)
    if not s or not s.shop_domain or not s.access_token:
        raise HTTPException(422, "Shopify is not configured yet")

    client = ShopifyClient(s.shop_domain, decrypt_secret_safe(s.access_token))
    catalog, sold_count = _catalog_for_publish(current_user.id, session)

    created = updated = 0
    errors: list[str] = []

    for entry in catalog:
        if entry["sold"]:
            continue
        product = _build_shopify_product(entry)
        mapping = session.exec(
            select(ShopifyProductMapping).where(
                ShopifyProductMapping.user_id == current_user.id,
                ShopifyProductMapping.catalog_id == entry["id"],
            )
        ).first()
        try:
            if mapping:
                client.update_product(mapping.shopify_product_id, product)
                mapping.updated_at = datetime.utcnow().isoformat()
                session.add(mapping)
                updated += 1
            else:
                result = client.create_product(product)
                session.add(ShopifyProductMapping(
                    user_id=current_user.id,
                    catalog_id=entry["id"],
                    shopify_product_id=str(result["id"]),
                ))
                created += 1
        except ShopifyAPIError as exc:
            errors.append(f"{entry['id']}: {exc}")

    published = (created + updated) > 0
    if published:
        s.last_published_at = datetime.utcnow().isoformat()
        s.updated_at = datetime.utcnow().isoformat()
        session.add(s)
    session.commit()

    write_audit_log(
        session,
        action="shopify.publish",
        user=current_user,
        target=f"user:{current_user.id}",
        request=request,
        success=published,
        detail=(
            f"created {created}, updated {updated}, skipped {sold_count} sold"
            + (f"; {len(errors)} error(s)" if errors else "")
        ),
    )

    return ShopifyPublishResult(
        published=published,
        created_count=created,
        updated_count=updated,
        skipped_count=sold_count,
        error=errors[0] if errors and not published else None,
        errors=errors,
    )
