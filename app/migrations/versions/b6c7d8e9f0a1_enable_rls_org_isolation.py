"""enable Row-Level Security org isolation (pool tenancy)

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-06-17

Changes (see the pool_vs_silo design memory):
  - Creates the non-superuser application role `opama_app` and an org-isolation
    RLS policy on every org-scoped table, so a shared Postgres can't leak rows
    across tenants even if a query forgets its `WHERE org_id = …`.
  - Each policy keys on the per-request GUC `app.current_org_id`
    (`current_setting('app.current_org_id', true)::int`), which the app sets via
    services/shared/rls.py. The `true` (missing_ok) makes an unset GUC resolve to
    NULL → the policy matches no rows: RLS fails *closed*.
  - Policies use the same expression for USING (SELECT/UPDATE/DELETE visibility)
    and WITH CHECK (INSERT/UPDATE target), so an org can neither read nor write
    another org's rows.

Enforcement model — important:
  RLS does NOT apply to superusers or table owners. The running app currently
  connects as the superuser `opama_user`, which BYPASSES RLS, so this migration is
  a NON-breaking no-op for the live container. Enforcement turns on only when
  DATABASE_URL is pointed at a non-superuser login role that inherits `opama_app`
  (the deployment seam). `opama_app` is created NOLOGIN/password-less here (no
  secret in the migration); deployment creates a LOGIN user and `GRANT opama_app
  TO that_user`.

Scope: the 23 org_id-bearing tables. Catalog tables (card/set — public read),
identity/mapping tables (user, organization, membership, …), and child tables
without org_id (deckcard, showcasecard, customassetfield, identificationattempt —
reached via an org-scoped parent) are intentionally NOT under org RLS here.

Postgres-only: skipped entirely on SQLite (test/dev-lite) binds.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "b6c7d8e9f0a1"
down_revision: Union[str, None] = "a5b6c7d8e9f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


APP_ROLE = "opama_app"
POLICY = "org_isolation"
GUC_EXPR = "current_setting('app.current_org_id', true)::int"

# The 23 org_id-bearing user-scoped tables (matches a5b6c7d8e9f0 / the org_id
# add-column batches). Child tables without org_id are excluded by design.
_TABLES: tuple[str, ...] = (
    "customasset",
    "genericasset",
    "showcase",
    "inventoryitem",
    "deck",
    "wishlist",
    "trade_items",
    "storefrontsettings",
    "saletransaction",
    "insurancepolicy",
    "appraisal",
    "policyitem",
    "mortgageloan",
    "propertyvaluation",
    "propertytaxrecord",
    "servicerecord",
    "vehicledocument",
    "shopifysettings",
    "shopifyproductmapping",
    "cardgraderesult",
    "gradefeedback",
    "portfoliosnapshot",
    "userportfoliosettings",
)


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        return

    # Non-superuser application role (idempotent, NOLOGIN group role — no secret).
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                CREATE ROLE {APP_ROLE} NOLOGIN;
            END IF;
        END $$;
        """
    )

    # Privileges: the app role needs DML on every table it touches (org-scoped
    # tables, identity/mapping tables, and read on the public catalog). RLS — not
    # GRANTs — provides the per-org isolation on the scoped tables.
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE};")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE};")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE};")
    # Future tables created by migrations (run as the owner) inherit these grants.
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE};"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE};"
    )

    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"DROP POLICY IF EXISTS {POLICY} ON {table};")
        op.execute(
            f"""
            CREATE POLICY {POLICY} ON {table}
                USING (org_id = {GUC_EXPR})
                WITH CHECK (org_id = {GUC_EXPR});
            """
        )


def downgrade() -> None:
    if not _is_postgres():
        return

    for table in _TABLES:
        op.execute(f"DROP POLICY IF EXISTS {POLICY} ON {table};")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    # Revoke privileges but leave the role in place — it may have been GRANTed to a
    # login user that still exists; dropping it would fail. Role removal is an
    # explicit ops action, not part of a schema downgrade.
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {APP_ROLE};"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f"REVOKE USAGE, SELECT ON SEQUENCES FROM {APP_ROLE};"
    )
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {APP_ROLE};")
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {APP_ROLE};")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {APP_ROLE};")
