"""
Generic per-plugin extension storage.

PluginData is the additive, no-new-migration persistence channel described in
docs/MODULE_DEVELOPMENT.md §4(A) — modules that just need a settings blob,
instance-wide config, or per-entity extension fields can read/write a JSON
column on this single shared table instead of defining their own SQLModel
table + Alembic migration. Modules with genuinely relational needs (typed
columns, FK joins, high write volume) should still use `model_modules` +
their own table; see §4(B).

Secrets do NOT go here — use services.shared.user_secrets (UserSecret).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, JSON, UniqueConstraint
from sqlmodel import Field, SQLModel


class PluginData(SQLModel, table=True):
    """
    One JSON blob per (plugin_id, entity_type, entity_id).

    entity_type/entity_id give three scope shapes:
      - ("user", user.id)        -> per-user settings (non-secret fields)
      - ("instance", 0)          -> instance-wide config, mutable via UI
      - (<table_name>, row.id)   -> per-entity extension fields, e.g.
                                     ("customasset", asset.id)
    """

    __tablename__ = "plugin_data"
    __table_args__ = (
        UniqueConstraint("plugin_id", "entity_type", "entity_id", name="uq_plugin_data_scope"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    plugin_id: str = Field(index=True)        # plugin.yaml `id`, e.g. "shopify"
    entity_type: str = Field(index=True)      # "user" | "instance" | "<table_name>"
    entity_id: int = Field(default=0, index=True)
    data: dict = Field(default_factory=dict, sa_column=Column(JSON))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
