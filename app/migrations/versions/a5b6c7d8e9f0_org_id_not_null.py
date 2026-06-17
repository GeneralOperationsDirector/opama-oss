"""flip org_id NOT NULL on every user-scoped table (pool tenancy)

Revision ID: a5b6c7d8e9f0
Revises: f4a5b6c7d8e9
Create Date: 2026-06-17

Changes (see the pool_vs_silo design memory):
  - Completes the org_id rollout: org_id was added nullable + backfilled in
    e3f4a5b6c7d8 (vertical) and f4a5b6c7d8e9 (general-PAM). The router/write
    layer now sets org_id on every insert, so the tenancy scope key can become
    a hard NOT NULL invariant across all 23 user-scoped tables.
  - This is the prerequisite for the RLS rollout: a nullable org_id would be a
    policy hole (a NULL row escapes every `org_id = current_org` policy).

  Before flipping, we re-run the owner→personal-org backfill as an idempotent
  safety net (covers any rows written between the add-column migration and this
  one in an environment that wasn't fully caught up). If any row still has a
  NULL org_id after that — e.g. an orphaned user_id — the ALTER fails loudly,
  which is the desired behavior: better a blocked migration than a silent
  tenancy hole.

  identificationattempt is intentionally excluded — it has no user_id/org_id
  owner column (ground-truth child data of cardgraderesult; RLS reaches it via
  the parent).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a5b6c7d8e9f0"
down_revision: Union[str, None] = "f4a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Every user-scoped table that carries org_id, across both add-column batches
# (e3f4a5b6c7d8 + f4a5b6c7d8e9). Order is irrelevant for the flip.
_TABLES: tuple[str, ...] = (
    # vertical batch (e3f4a5b6c7d8)
    "customasset",
    "genericasset",
    "showcase",
    "inventoryitem",
    "deck",
    "wishlist",
    "trade_items",
    "storefrontsettings",
    "saletransaction",
    # general-PAM batch (f4a5b6c7d8e9)
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


def upgrade() -> None:
    bind = op.get_bind()

    # Idempotent safety-net backfill: map any still-NULL row's owner (user_id) to
    # that user's personal org-of-one (created in d2e3f4a5b6c7). A no-op when the
    # add-column migrations already backfilled everything.
    for table in _TABLES:
        bind.execute(
            sa.text(
                f"""
                UPDATE {table} AS t
                SET org_id = m.org_id
                FROM membership m
                JOIN organization o
                    ON o.id = m.org_id AND o.is_personal = true
                WHERE m.user_id = t.user_id
                  AND t.org_id IS NULL
                """
            )
        )

    # Flip NOT NULL. Fails loudly if any row still has a NULL org_id (orphaned
    # owner) — that is a data-integrity stop, not something to paper over.
    for table in _TABLES:
        op.alter_column(table, "org_id", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    for table in _TABLES:
        op.alter_column(table, "org_id", existing_type=sa.Integer(), nullable=True)
