"""
SQLModel table for dynamically-installed plugins.

Plugins installed via POST /plugin-store/install are persisted here.
On the next app startup, load_dynamic_plugins() reads this table and
registers their proxy routes.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class DynamicPlugin(SQLModel, table=True):
    __tablename__ = "dynamic_plugins"

    id: Optional[int] = Field(default=None, primary_key=True)
    plugin_id: str = Field(unique=True, index=True)
    name: str
    description: str = ""
    type: str = "remote"          # remote | local
    tier: str = "free"            # core | free | premium | enterprise
    icon: str = ""
    version: str = "1.0.0"        # for type=local, the currently-installed version
    remote_url: str = ""          # required for type=remote
    auth_type: str = "none"       # none | signed_jwt
    api_prefix: str = ""
    tags_json: str = "[]"         # JSON-encoded list of tag strings
    scopes_json: str = "[]"       # JSON-encoded list of scope strings
    manifest_url: str = ""
    enabled: bool = True
    installed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # --- type=local fields (download-and-run in-process; see app/plugin_installer.py) ---
    download_url: str = ""        # required for type=local; SSRF-validated, license-gated
    install_path: str = ""        # absolute path to the extracted package on disk
    router_module: str = ""       # dotted module path imported at startup
    router_attr: str = "router"   # attribute on router_module holding the APIRouter
    model_modules_json: str = "[]"  # always "[]" in v1 — see plugin_installer for why

    @property
    def tags_list(self) -> list[str]:
        try:
            return json.loads(self.tags_json)
        except Exception:
            return []

    @property
    def scopes_list(self) -> list[str]:
        try:
            return json.loads(self.scopes_json)
        except Exception:
            return []

    @property
    def model_modules_list(self) -> list[str]:
        try:
            return json.loads(self.model_modules_json)
        except Exception:
            return []
