"""add org trade_discoverable flag + RLS discovery-read policies

Revision ID: 7e2d1c9b4a30
Revises: e0f1a2b3c4d5
Create Date: 2026-06-18

The cross-user trade matching feature (the pool's flagship social feature) needs
to read *other* orgs' trade lists / wishlists — which org_isolation RLS would
otherwise hide. Rather than a blanket bypass, gate it on explicit opt-in:

  - `organization.trade_discoverable` (default false): when an owner opts in,
    that org's trade_items + wishlist become readable by the matching engine.
  - SELECT-only RLS policies `trade_discovery_read` / `wishlist_discovery_read`
    on those two tables: OR-combined with org_isolation, a row is readable when
    it's your own org's OR the owning org has opted into discovery. Writes stay
    org-only (org_isolation WITH CHECK is unchanged).

Postgres-only for the policies; the column add runs on any backend.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7e2d1c9b4a30"
down_revision: Union[str, None] = "e0f1a2b3c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_POLICIES = (
    ("trade_discovery_read", "trade_items"),
    ("wishlist_discovery_read", "wishlist"),
)


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.add_column(
        "organization",
        sa.Column("trade_discoverable", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    if not _is_postgres():
        return
    for policy, table in _POLICIES:
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {table};")
        op.execute(
            f"""
            CREATE POLICY {policy} ON {table}
                FOR SELECT
                USING (EXISTS (
                    SELECT 1 FROM organization o
                    WHERE o.id = {table}.org_id AND o.trade_discoverable = true
                ));
            """
        )


def downgrade() -> None:
    if _is_postgres():
        for policy, table in _POLICIES:
            op.execute(f"DROP POLICY IF EXISTS {policy} ON {table};")
    op.drop_column("organization", "trade_discoverable")
