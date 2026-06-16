from typing import Optional
from pydantic import BaseModel


class ShopifySettingsIn(BaseModel):
    shop_domain: str = ""
    # Empty/omitted means "keep existing token, do not overwrite"
    access_token: Optional[str] = None


class ShopifySettingsOut(BaseModel):
    id: int
    user_id: int
    shop_domain: str
    # Token is never returned in full — only a masked hint and a boolean
    access_token_set: bool
    access_token_hint: Optional[str]  # last 4 chars, e.g. "…a4f2"
    last_published_at: Optional[str]
    created_at: str
    updated_at: str


class ShopifyPublishResult(BaseModel):
    published: bool
    created_count: int
    updated_count: int
    skipped_count: int
    error: Optional[str] = None
    errors: list[str] = []
