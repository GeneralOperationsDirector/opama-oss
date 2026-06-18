"""add per-org export_key to organization (pool tenancy)

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-06-18

Changes (see the pool_vs_silo design memory, RLS pre-activation checklist):
  - Replaces the single global WEBSITE_EXPORT_KEY for the storefront export
    endpoints with a per-organization key. Each org's storefront pull
    (GET /assets/website-listings) and sale webhook
    (POST /assets/website-listings/{slug}/sold) authenticate with this key; the
    endpoint resolves the org from it and stamps the RLS GUC, so the cross-org
    global key — which RLS would otherwise fail closed — is no longer needed and
    the per-org slug lookup is unambiguous.
  - Nullable + unique: existing orgs have no key until the owner generates one.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d9e0f1a2b3c4"
down_revision: Union[str, None] = "c8d9e0f1a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_IX = "ix_organization_export_key"


def upgrade() -> None:
    op.add_column("organization", sa.Column("export_key", sa.String(), nullable=True))
    op.create_index(_IX, "organization", ["export_key"], unique=True)


def downgrade() -> None:
    op.drop_index(_IX, table_name="organization")
    op.drop_column("organization", "export_key")
