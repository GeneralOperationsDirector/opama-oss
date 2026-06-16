"""
Shopify storefront-publish plugin — per-user settings and product mapping.

Owned by the `shopify` external plugin (external_plugins/opama_shopify/,
premium tier). Mirrors the StorefrontSettings pattern
(external_plugins/opama_storefront/models.py) for per-user settings with an
encrypted secret — see docs/MODULE_DEVELOPMENT.md "Settings & secrets".
"""

from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, UniqueConstraint


class ShopifySettings(SQLModel, table=True):
    """Per-user Shopify store configuration — one row per user."""

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, unique=True)

    shop_domain: str = Field(default="")  # e.g. "my-shop.myshopify.com"
    access_token: Optional[str] = None  # Admin API access token, encrypted at rest
    last_published_at: Optional[str] = None

    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class ShopifyProductMapping(SQLModel, table=True):
    """
    Remembers which Shopify product a storefront catalog entry was published
    as, so re-publishing updates that product instead of creating a duplicate.

    catalog_id is the storefront catalog entry's `id` field (the asset's
    website_slug, or its numeric id as a string when no slug is set — see
    `_build_catalog_entry()` in external_plugins/opama_storefront/router.py).
    """

    __table_args__ = (
        UniqueConstraint("user_id", "catalog_id", name="uq_shopify_mapping_user_catalog"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    catalog_id: str = Field(index=True)
    shopify_product_id: str
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
