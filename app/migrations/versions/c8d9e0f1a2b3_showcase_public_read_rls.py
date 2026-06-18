"""add a public-read RLS policy to showcase (pool tenancy)

Revision ID: c8d9e0f1a2b3
Revises: b6c7d8e9f0a1
Create Date: 2026-06-18

Changes (see the pool_vs_silo design memory, RLS pre-activation checklist):
  - `showcase` carries the org-isolation policy from b6c7d8e9f0a1, which keys on
    the per-request GUC `app.current_org_id`. But public showcases are read by
    anonymous visitors (GET /showcases/{id}, GET /showcases/public/{user_id})
    with no auth and therefore no org GUC — under RLS those reads would fail
    *closed* (0 rows), hiding world-readable content.
  - Add a second, SELECT-only permissive policy `showcase_public_read` with
    `USING (is_public = true)`. Permissive policies are OR-combined, so a row is
    visible for SELECT when it belongs to the active org *or* is public. Writes
    (INSERT/UPDATE/DELETE) remain governed solely by `org_isolation` — public
    means readable, never writable.

  Hydrating a public showcase's cards still reads org-scoped tables
  (customasset); the read paths stamp the showcase's own org for that, so this
  policy only needs to unlock the `showcase` rows themselves.

Postgres-only: a no-op on SQLite (test/dev-lite) binds.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, None] = "b6c7d8e9f0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PUBLIC_POLICY = "showcase_public_read"


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        return
    op.execute(f"DROP POLICY IF EXISTS {PUBLIC_POLICY} ON showcase;")
    op.execute(
        f"""
        CREATE POLICY {PUBLIC_POLICY} ON showcase
            FOR SELECT
            USING (is_public = true);
        """
    )


def downgrade() -> None:
    if not _is_postgres():
        return
    op.execute(f"DROP POLICY IF EXISTS {PUBLIC_POLICY} ON showcase;")
