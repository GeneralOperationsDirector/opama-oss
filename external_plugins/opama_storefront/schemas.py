from typing import Optional
from pydantic import BaseModel


class StorefrontSettingsIn(BaseModel):
    site_name: str = "My Shop"
    site_url: str = ""
    public_api_url: str = ""
    catalog_path: Optional[str] = None
    webhook_url: Optional[str] = None
    # GitHub — empty string means "keep existing token, do not overwrite"
    github_token: Optional[str] = None
    github_repo: Optional[str] = None
    github_file_path: Optional[str] = None
    github_commit_message: Optional[str] = None


class StorefrontSettingsOut(BaseModel):
    id: int
    user_id: int
    site_name: str
    site_url: str
    public_api_url: str
    catalog_path: Optional[str]
    webhook_url: Optional[str]
    # Token is never returned in full — only a masked hint and a boolean
    github_token_set: bool
    github_token_hint: Optional[str]   # last 4 chars, e.g. "…a4f2"
    github_repo: Optional[str]
    github_file_path: Optional[str]
    github_commit_message: Optional[str]
    last_published_at: Optional[str]
    created_at: str
    updated_at: str


class GitHubTestRequest(BaseModel):
    # Both optional — falls back to the saved settings when omitted, so the
    # button works both for unsaved edits and already-configured settings.
    github_token: Optional[str] = None
    github_repo: Optional[str] = None


class GitHubTestResult(BaseModel):
    connected: bool
    repo_full_name: Optional[str] = None
    private: Optional[bool] = None
    can_push: Optional[bool] = None
    error: Optional[str] = None


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
