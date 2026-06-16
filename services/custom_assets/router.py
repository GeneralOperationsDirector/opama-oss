"""
Collections (custom assets) API router — mounted at /assets.

The core of the whitelabel product: tracking items of any asset class. Owns
CRUD plus image upload (front/back, with auto-thumbnails), the portfolio
`/summary`, and the two `X-Export-Key`-authenticated `/website-listings`
endpoints the external storefront site pulls from and posts sales back to.
Auth + ownership are enforced on every user-data route via `_assert_owner()`;
static routes (`/summary`, `/website-listings`) are declared before the
dynamic `/{asset_id}` route so they aren't shadowed.
"""
import io
import os
from datetime import datetime, date
from hmac import compare_digest
from pathlib import Path
from typing import Optional

from PIL import Image

from fastapi import APIRouter, Depends, File, HTTPException, Query, Security, UploadFile
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel as _BM
from sqlmodel import Session, select

from services.shared.database import get_session
from services.shared.models import User
from services.auth.middleware import get_current_user
from .models import CustomAsset, CustomAssetField
from .schemas import (
    CustomAssetCreate,
    CustomAssetOut,
    CustomAssetUpdate,
    CustomFieldOut,
    PortfolioSummary,
    WebsiteListing,
)

router = APIRouter(prefix="/assets", tags=["custom-assets"])

_ASSET_UPLOADS = Path("/app/uploads/assets")
_PUBLIC_API_URL = os.environ.get("PUBLIC_API_URL", "").rstrip("/")
_IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
_MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB
_THUMB_WIDTH = 300


def _make_thumbnail(raw: bytes) -> bytes:
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    ratio = _THUMB_WIDTH / img.width
    img = img.resize((_THUMB_WIDTH, int(img.height * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=82, optimize=True)
    return buf.getvalue()


def _cleanup_asset_images(asset_id: int) -> None:
    for pattern in (f"{asset_id}.*", f"{asset_id}_thumb.jpg", f"{asset_id}_back.*", f"{asset_id}_back_thumb.jpg"):
        for f in _ASSET_UPLOADS.glob(pattern):
            f.unlink(missing_ok=True)


def _abs_image_url(url: Optional[str]) -> Optional[str]:
    """Return an absolute URL for an image path — needed for website listings."""
    if not url:
        return None
    if url.startswith("http"):
        return url
    return f"{_PUBLIC_API_URL}{url}" if _PUBLIC_API_URL else url


# ---------------------------------------------------------------------------
# API-key auth (used by website-listings endpoints only — no Firebase needed)
# ---------------------------------------------------------------------------

_export_key_header = APIKeyHeader(name="X-Export-Key", auto_error=False)


def _require_export_key(api_key: Optional[str] = Security(_export_key_header)) -> None:
    expected = os.environ.get("WEBSITE_EXPORT_KEY", "")
    if not expected:
        raise HTTPException(503, "Export key not configured on server")
    # compare_digest prevents timing-based brute-force attacks
    if not compare_digest(api_key or "", expected):
        raise HTTPException(401, "Invalid export key")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _hydrate(asset: CustomAsset, session: Session) -> CustomAssetOut:
    fields = session.exec(
        select(CustomAssetField).where(CustomAssetField.asset_id == asset.id)
    ).all()
    return CustomAssetOut(
        **asset.model_dump(),
        custom_fields=[CustomFieldOut(id=f.id, key=f.key, value=f.value) for f in fields],
    )


def _assert_owner(asset: CustomAsset, current_user: User) -> None:
    if asset.user_id != current_user.id:
        raise HTTPException(403, "Cannot access another user's asset")


# Also imported by external_plugins/opama_storefront/router.py to normalize
# catalog-entry categories — keep this signature/mapping stable, or update
# that plugin in lockstep.
def _category_slug(raw: str) -> str:
    """Normalise opama free-text category to a storefront catalog slug."""
    mapping = {
        "trading cards": "trading-cards",
        "trading card":  "trading-cards",
        "cards":         "trading-cards",
        "comics":        "comics",
        "comic":         "comics",
        "comic book":    "comics",
        "coins":         "coins",
        "coin":          "coins",
        "jewelry":       "jewelry",
        "jewellery":     "jewelry",
        "jewlery":       "jewelry",
    }
    return mapping.get(raw.lower().strip(), raw.lower().replace(" ", "-"))


def _to_website_listing(asset: CustomAsset, fields: list[CustomAssetField]) -> WebsiteListing:
    field_map = {f.key: f.value for f in fields}
    mp_keys = ("ebay", "facebook", "kijiji", "craigslist")
    return WebsiteListing(
        id=asset.website_slug or str(asset.id),
        title=asset.name,
        category=_category_slug(asset.category),
        condition=asset.condition or "",
        description=asset.description or "",
        priceCad=asset.listing_price_cad or 0.0,
        shippingCad=asset.shipping_price_cad or 0.0,
        images=[u for u in [_abs_image_url(asset.image_url), _abs_image_url(asset.back_image_url)] if u],
        sold=bool(asset.sale_date),
        marketplaceLinks={
            k: (getattr(asset, f"marketplace_{k}", None) or field_map.get(k, "")) or ""
            for k in mp_keys
        },
    )


# ---------------------------------------------------------------------------
# List & search  (static routes — must come before /{asset_id})
# ---------------------------------------------------------------------------

@router.get("", response_model=list[CustomAssetOut])
def list_assets(
    category: Optional[str] = Query(None),
    q: Optional[str] = Query(None, max_length=200),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    stmt = select(CustomAsset).where(CustomAsset.user_id == current_user.id)
    if category:
        stmt = stmt.where(CustomAsset.category == category)
    if q:
        stmt = stmt.where(CustomAsset.name.ilike(f"%{q}%"))
    stmt = stmt.offset(offset).limit(limit)
    assets = session.exec(stmt).all()
    return [_hydrate(a, session) for a in assets]


@router.get("/categories", response_model=list[str])
def list_categories(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    rows = session.exec(
        select(CustomAsset.category)
        .where(CustomAsset.user_id == current_user.id)
        .distinct()
    ).all()
    return sorted(rows)


@router.get("/summary", response_model=PortfolioSummary)
def portfolio_summary(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    assets = session.exec(
        select(CustomAsset).where(CustomAsset.user_id == current_user.id)
    ).all()

    total_cost = sum((a.purchase_price or 0) * a.quantity for a in assets)
    total_value = sum((a.estimated_value or a.purchase_price or 0) * a.quantity for a in assets)

    cat_map: dict[str, dict] = {}
    for a in assets:
        c = cat_map.setdefault(a.category, {"category": a.category, "count": 0, "value": 0.0})
        c["count"] += a.quantity
        c["value"] += (a.estimated_value or a.purchase_price or 0) * a.quantity

    return PortfolioSummary(
        total_assets=sum(a.quantity for a in assets),
        total_cost=total_cost,
        total_estimated_value=total_value,
        unrealized_gain=total_value - total_cost,
        categories=list(cat_map.values()),
    )


# ---------------------------------------------------------------------------
# Website export — static routes, API-key auth, no Firebase required
# Called by the storefront site's admin tool / Cloudflare worker.
# MUST stay above /{asset_id} to avoid route collision.
# ---------------------------------------------------------------------------

@router.get("/website-listings", response_model=list[WebsiteListing])
def website_listings(
    session: Session = Depends(get_session),
    _: None = Depends(_require_export_key),
):
    """Return all assets marked listed_on_website=True in catalog.json format."""
    assets = session.exec(
        select(CustomAsset).where(CustomAsset.listed_on_website == True)  # noqa: E712
    ).all()

    result = []
    for asset in assets:
        fields = session.exec(
            select(CustomAssetField).where(CustomAssetField.asset_id == asset.id)
        ).all()
        result.append(_to_website_listing(asset, fields))
    return result


class SaleRecord(_BM):
    sale_price_cad: float
    sale_platform: str = "website"


@router.post("/website-listings/{website_slug}/sold", status_code=200)
def record_sale(
    website_slug: str,
    body: SaleRecord,
    session: Session = Depends(get_session),
    _: None = Depends(_require_export_key),
):
    """
    Mark an asset sold and record the sale price.
    Called by the storefront site's Stripe webhook after checkout.session.completed.
    """
    asset = session.exec(
        select(CustomAsset).where(CustomAsset.website_slug == website_slug)
    ).first()
    if not asset:
        raise HTTPException(404, f"No asset with website_slug '{website_slug}'")

    asset.sale_price_cad = body.sale_price_cad
    asset.sale_date = date.today().isoformat()
    asset.sale_platform = body.sale_platform
    asset.updated_at = datetime.utcnow().isoformat()
    session.add(asset)
    session.commit()
    return {"ok": True, "slug": website_slug, "sale_price_cad": body.sale_price_cad}


# ---------------------------------------------------------------------------
# Single asset  (dynamic route — must come after all static routes)
# ---------------------------------------------------------------------------

@router.get("/{asset_id}", response_model=CustomAssetOut)
def get_asset(
    asset_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    asset = session.get(CustomAsset, asset_id)
    if not asset:
        raise HTTPException(404, f"Asset {asset_id} not found")
    _assert_owner(asset, current_user)
    return _hydrate(asset, session)


@router.post("", response_model=CustomAssetOut, status_code=201)
def create_asset(
    body: CustomAssetCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    asset = CustomAsset(
        user_id=current_user.id,
        name=body.name,
        category=body.category,
        condition=body.condition,
        quantity=body.quantity,
        purchase_price=body.purchase_price,
        purchase_date=body.purchase_date,
        estimated_value=body.estimated_value,
        description=body.description,
        image_url=body.image_url,
        tags=body.tags,
        listed_on_website=body.listed_on_website,
        listing_price_cad=body.listing_price_cad,
        shipping_price_cad=body.shipping_price_cad,
        website_slug=body.website_slug,
    )
    session.add(asset)
    session.commit()
    session.refresh(asset)

    for f in body.custom_fields:
        session.add(CustomAssetField(asset_id=asset.id, key=f.key, value=f.value))
    session.commit()

    return _hydrate(asset, session)


@router.patch("/{asset_id}", response_model=CustomAssetOut)
def update_asset(
    asset_id: int,
    body: CustomAssetUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    asset = session.get(CustomAsset, asset_id)
    if not asset:
        raise HTTPException(404, f"Asset {asset_id} not found")
    _assert_owner(asset, current_user)

    updates = body.model_dump(exclude_unset=True, exclude={"custom_fields"})
    for field, val in updates.items():
        setattr(asset, field, val)
    # If a URL is explicitly cleared, drop its thumbnail too
    if updates.get("image_url") is None and "image_url" in updates:
        asset.image_thumb_url = None
    if updates.get("back_image_url") is None and "back_image_url" in updates:
        asset.back_image_thumb_url = None
    asset.updated_at = datetime.utcnow().isoformat()

    if body.custom_fields is not None:
        existing = session.exec(
            select(CustomAssetField).where(CustomAssetField.asset_id == asset_id)
        ).all()
        for f in existing:
            session.delete(f)
        for f in body.custom_fields:
            session.add(CustomAssetField(asset_id=asset_id, key=f.key, value=f.value))

    session.add(asset)
    session.commit()
    session.refresh(asset)
    return _hydrate(asset, session)


@router.delete("/{asset_id}", status_code=204)
def delete_asset(
    asset_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    asset = session.get(CustomAsset, asset_id)
    if not asset:
        raise HTTPException(404, f"Asset {asset_id} not found")
    _assert_owner(asset, current_user)

    fields = session.exec(
        select(CustomAssetField).where(CustomAssetField.asset_id == asset_id)
    ).all()
    for f in fields:
        session.delete(f)
    session.flush()  # send field deletes before the FK-constrained asset delete
    session.delete(asset)
    session.commit()
    _cleanup_asset_images(asset_id)


@router.post("/{asset_id}/image")
async def upload_asset_image(
    asset_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Upload the front image for an asset. Generates a thumbnail automatically."""
    asset = session.get(CustomAsset, asset_id)
    if not asset:
        raise HTTPException(404, f"Asset {asset_id} not found")
    _assert_owner(asset, current_user)

    ext = _IMAGE_TYPES.get(file.content_type or "")
    if not ext:
        raise HTTPException(400, "Image must be JPEG, PNG, or WebP")

    raw = await file.read()
    if len(raw) > _MAX_IMAGE_BYTES:
        raise HTTPException(413, "Image exceeds 10 MB limit")

    _ASSET_UPLOADS.mkdir(parents=True, exist_ok=True)
    (_ASSET_UPLOADS / f"{asset_id}{ext}").write_bytes(raw)
    (_ASSET_UPLOADS / f"{asset_id}_thumb.jpg").write_bytes(_make_thumbnail(raw))

    image_url = f"/uploads/assets/{asset_id}{ext}"
    thumb_url = f"/uploads/assets/{asset_id}_thumb.jpg"
    asset.image_url = image_url
    asset.image_thumb_url = thumb_url
    asset.updated_at = datetime.utcnow().isoformat()
    session.add(asset)
    session.commit()
    return {"image_url": image_url, "image_thumb_url": thumb_url}


@router.post("/{asset_id}/back-image")
async def upload_asset_back_image(
    asset_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Upload the back image for an asset. Generates a thumbnail automatically."""
    asset = session.get(CustomAsset, asset_id)
    if not asset:
        raise HTTPException(404, f"Asset {asset_id} not found")
    _assert_owner(asset, current_user)

    ext = _IMAGE_TYPES.get(file.content_type or "")
    if not ext:
        raise HTTPException(400, "Image must be JPEG, PNG, or WebP")

    raw = await file.read()
    if len(raw) > _MAX_IMAGE_BYTES:
        raise HTTPException(413, "Image exceeds 10 MB limit")

    _ASSET_UPLOADS.mkdir(parents=True, exist_ok=True)
    (_ASSET_UPLOADS / f"{asset_id}_back{ext}").write_bytes(raw)
    (_ASSET_UPLOADS / f"{asset_id}_back_thumb.jpg").write_bytes(_make_thumbnail(raw))

    back_image_url = f"/uploads/assets/{asset_id}_back{ext}"
    back_thumb_url = f"/uploads/assets/{asset_id}_back_thumb.jpg"
    asset.back_image_url = back_image_url
    asset.back_image_thumb_url = back_thumb_url
    asset.updated_at = datetime.utcnow().isoformat()
    session.add(asset)
    session.commit()
    return {"back_image_url": back_image_url, "back_image_thumb_url": back_thumb_url}
