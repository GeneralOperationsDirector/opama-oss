from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field


class CustomAsset(SQLModel, table=True):
    """
    A user-defined asset of any type. Covers anything not handled by a
    dedicated module (guitars, wine, watches, sneakers, etc.).
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)

    name: str
    category: str  # free-text, e.g. "Guitar", "Wine", "Watch"
    condition: Optional[str] = None  # e.g. "Mint", "Good", "Fair"
    quantity: int = Field(default=1)

    purchase_price: Optional[float] = None
    purchase_date: Optional[str] = None   # ISO date YYYY-MM-DD
    estimated_value: Optional[float] = None

    description: Optional[str] = None
    image_url: Optional[str] = None
    image_thumb_url: Optional[str] = None
    back_image_url: Optional[str] = None
    back_image_thumb_url: Optional[str] = None
    tags: Optional[str] = None  # comma-separated

    # ── Marketplace links (dedicated fields for storefront export) ───────────
    marketplace_ebay: Optional[str] = None
    marketplace_facebook: Optional[str] = None
    marketplace_kijiji: Optional[str] = None
    marketplace_craigslist: Optional[str] = None

    # ── Website listing ───────────────────────────────────────────────────────
    listed_on_website: bool = Field(default=False)
    listing_price_cad: Optional[float] = None   # asking price on the storefront site
    shipping_price_cad: Optional[float] = None  # flat shipping shown at checkout
    website_slug: Optional[str] = None          # catalog.json id (e.g. "1952-mantle-311")

    # ── Sale recording (filled by the storefront webhook after Stripe sale) ───
    sale_price_cad: Optional[float] = None
    sale_date: Optional[str] = None       # ISO date YYYY-MM-DD
    sale_platform: Optional[str] = None   # e.g. "website", "ebay", "local"

    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class CustomAssetField(SQLModel, table=True):
    """
    Arbitrary key/value metadata attached to a CustomAsset.
    Lets users store domain-specific data without schema changes.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    asset_id: int = Field(foreign_key="customasset.id", index=True)
    key: str
    value: str
