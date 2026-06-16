from typing import Optional
from pydantic import BaseModel


class StorefrontSettingsIn(BaseModel):
    site_name: str = "My Shop"
    site_url: str = ""
    public_api_url: str = ""
    catalog_path: Optional[str] = None
    webhook_url: Optional[str] = None


class StorefrontSettingsOut(BaseModel):
    id: int
    user_id: int
    site_name: str
    site_url: str
    public_api_url: str
    catalog_path: Optional[str]
    webhook_url: Optional[str]
    last_published_at: Optional[str]
    created_at: str
    updated_at: str


class ImageUrlTestRequest(BaseModel):
    public_api_url: str


class ImageUrlTestResult(BaseModel):
    reachable: bool
    tested_url: str
    status_code: Optional[int] = None
    content_type: Optional[str] = None
    error: Optional[str] = None


class StorefrontListingPatch(BaseModel):
    listing_price_cad: Optional[float] = None
    shipping_price_cad: Optional[float] = None
    website_slug: Optional[str] = None
    marketplace_ebay: Optional[str] = None
    marketplace_facebook: Optional[str] = None
    marketplace_kijiji: Optional[str] = None
    marketplace_craigslist: Optional[str] = None


class PublishResult(BaseModel):
    published: bool
    item_count: int
    sold_count: int
    last_published_at: Optional[str]
    error: Optional[str]
    catalog: list[dict]
    github_commit_url: Optional[str] = None
