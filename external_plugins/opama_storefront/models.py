from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field


class StorefrontSettings(SQLModel, table=True):
    """Per-user storefront configuration — one row per user.

    Migrating to org-owned (pool tenancy — see pool_vs_silo): a store's settings
    belong to the Organization so staff share one storefront config. org_id is
    nullable through the backfill migration; user_id stays as the acting user.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    org_id: int = Field(foreign_key="organization.id", index=True)
    user_id: int = Field(index=True, unique=True)

    site_name: str = Field(default="My Shop")
    site_url: str = Field(default="")
    public_api_url: str = Field(default="")

    # Where to push catalog.json on publish.
    # catalog_path: absolute filesystem path (for local deployments)
    # webhook_url:  HTTP endpoint that accepts POST {catalog: [...]}
    catalog_path: Optional[str] = None
    webhook_url: Optional[str] = None

    last_published_at: Optional[str] = None

    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
