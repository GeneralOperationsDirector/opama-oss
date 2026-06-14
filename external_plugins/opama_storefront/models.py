from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field


class StorefrontSettings(SQLModel, table=True):
    """Per-user storefront configuration — one row per user."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, unique=True)

    site_name: str = Field(default="My Shop")
    site_url: str = Field(default="")
    public_api_url: str = Field(default="")

    # Where to push catalog.json on publish.
    # catalog_path: absolute filesystem path (for local deployments)
    # webhook_url:  HTTP endpoint that accepts POST {catalog: [...]}
    catalog_path: Optional[str] = None
    webhook_url: Optional[str] = None

    # GitHub publishing — commits catalog.json directly to the repo,
    # triggering an automatic Cloudflare Pages deploy.
    github_token: Optional[str] = None          # Personal Access Token (contents:write)
    github_repo: Optional[str] = None           # e.g. "youruser/yourshop-site"
    github_file_path: Optional[str] = None      # e.g. "public/collectibles/catalog.json"
    github_commit_message: Optional[str] = None # template; {n} = item count

    last_published_at: Optional[str] = None

    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
