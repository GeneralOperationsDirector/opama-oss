from typing import Optional
from pydantic import BaseModel, Field


class CustomFieldIn(BaseModel):
    key: str = Field(..., min_length=1, max_length=100)
    value: str = Field(..., max_length=2000)


class CustomAssetCreate(BaseModel):
    user_id: Optional[int] = None  # ignored; user is inferred from auth token
    name: str
    category: str
    condition: Optional[str] = None
    quantity: int = 1
    purchase_price: Optional[float] = None
    purchase_date: Optional[str] = None
    estimated_value: Optional[float] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    back_image_url: Optional[str] = None
    tags: Optional[str] = None
    marketplace_ebay: Optional[str] = None
    marketplace_facebook: Optional[str] = None
    marketplace_kijiji: Optional[str] = None
    marketplace_craigslist: Optional[str] = None
    custom_fields: list[CustomFieldIn] = []
    # Website listing
    listed_on_website: bool = False
    listing_price_cad: Optional[float] = None
    shipping_price_cad: Optional[float] = None
    website_slug: Optional[str] = None


class CustomAssetUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    condition: Optional[str] = None
    quantity: Optional[int] = None
    purchase_price: Optional[float] = None
    purchase_date: Optional[str] = None
    estimated_value: Optional[float] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    back_image_url: Optional[str] = None
    tags: Optional[str] = None
    marketplace_ebay: Optional[str] = None
    marketplace_facebook: Optional[str] = None
    marketplace_kijiji: Optional[str] = None
    marketplace_craigslist: Optional[str] = None
    custom_fields: Optional[list[CustomFieldIn]] = None
    # Website listing
    listed_on_website: Optional[bool] = None
    listing_price_cad: Optional[float] = None
    shipping_price_cad: Optional[float] = None
    website_slug: Optional[str] = None
    # Sale recording
    sale_price_cad: Optional[float] = None
    sale_date: Optional[str] = None
    sale_platform: Optional[str] = None


class CustomFieldOut(BaseModel):
    id: int
    key: str
    value: str


class CustomAssetOut(BaseModel):
    id: int
    user_id: int
    name: str
    category: str
    condition: Optional[str]
    quantity: int
    purchase_price: Optional[float]
    purchase_date: Optional[str]
    estimated_value: Optional[float]
    description: Optional[str]
    image_url: Optional[str]
    image_thumb_url: Optional[str]
    back_image_url: Optional[str]
    back_image_thumb_url: Optional[str]
    tags: Optional[str]
    marketplace_ebay: Optional[str]
    marketplace_facebook: Optional[str]
    marketplace_kijiji: Optional[str]
    marketplace_craigslist: Optional[str]
    created_at: str
    updated_at: str
    custom_fields: list[CustomFieldOut] = []
    # Website listing
    listed_on_website: bool
    listing_price_cad: Optional[float]
    shipping_price_cad: Optional[float]
    website_slug: Optional[str]
    # Sale recording
    sale_price_cad: Optional[float]
    sale_date: Optional[str]
    sale_platform: Optional[str]


class WebsiteListing(BaseModel):
    """catalog.json-compatible format consumed by the storefront site."""
    id: str
    title: str
    category: str
    condition: str
    description: str
    priceCad: float
    shippingCad: float
    images: list[str]
    sold: bool
    marketplaceLinks: dict[str, str]


class PortfolioSummary(BaseModel):
    total_assets: int
    total_cost: float
    total_estimated_value: float
    unrealized_gain: float
    categories: list[dict]
