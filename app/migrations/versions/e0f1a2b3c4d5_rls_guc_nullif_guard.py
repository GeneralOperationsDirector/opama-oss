"""harden RLS org GUC cast against empty-string ('') — NULLIF guard

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
Create Date: 2026-06-18

Why (found by the dev-stack RLS validation):
  The org_isolation policy from b6c7d8e9f0a1 keyed on
  ``current_setting('app.current_org_id', true)::int``. The ``true`` (missing_ok)
  returns NULL only while the custom GUC has *never* been set on a connection.
  But once any request stamps it (``set_config(..., is_local => true)`` ≡
  SET LOCAL), after that transaction ends the session-level value of a custom
  ``app.*`` GUC reverts to the **empty string** ``''`` — not NULL. On a pooled
  connection the next *unstamped* query (e.g. the public-showcase read, which
  relies on showcase_public_read rather than a GUC) then evaluates
  ``''::int`` → `invalid input syntax for type integer: ""` and the query errors
  out instead of failing closed.

Fix: wrap the read in ``NULLIF(current_setting('app.current_org_id', true), '')``
so both "never set" (NULL) and "reverted to empty" ('') collapse to NULL →
``NULL::int`` → the policy matches no rows (fails closed) and never raises.

Re-creates the org_isolation policy on all 23 org-scoped tables with the guarded
expression. Postgres-only; no-op on SQLite.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "e0f1a2b3c4d5"
down_revision: Union[str, None] = "d9e0f1a2b3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

POLICY = "org_isolation"
# Guarded read: '' (reverted custom GUC) and NULL (never set) both → NULL → no rows.
GUC_EXPR = "NULLIF(current_setting('app.current_org_id', true), '')::int"
# The original, unguarded expression (for downgrade).
OLD_GUC_EXPR = "current_setting('app.current_org_id', true)::int"

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


def _recreate(expr: str) -> None:
    for table in _TABLES:
        op.execute(f"DROP POLICY IF EXISTS {POLICY} ON {table};")
        op.execute(
            f"""
            CREATE POLICY {POLICY} ON {table}
                USING (org_id = {expr})
                WITH CHECK (org_id = {expr});
            """
        )


def upgrade() -> None:
    if not _is_postgres():
        return
    _recreate(GUC_EXPR)


def downgrade() -> None:
    if not _is_postgres():
        return
    _recreate(OLD_GUC_EXPR)
