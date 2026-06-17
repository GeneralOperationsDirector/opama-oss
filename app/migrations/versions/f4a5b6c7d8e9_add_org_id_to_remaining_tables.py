"""add org_id to remaining user-scoped tables (general-PAM batch)

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-06-17

Changes (see the pool_vs_silo design memory):
  - Completes the org_id rollout begun in e3f4a5b6c7d8, covering the general-PAM
    modules outside the Pokémon vertical so the tenancy scope key is *uniform*
    across every user-scoped table (a prerequisite for the RLS rollout — a table
    without org_id would be a policy hole).
  - Tables: insurancepolicy, appraisal, policyitem, mortgageloan,
    propertyvaluation, propertytaxrecord, servicerecord, vehicledocument,
    shopifysettings, shopifyproductmapping, cardgraderesult, gradefeedback,
    portfoliosnapshot, userportfoliosettings.
  - Same shape as the vertical batch: nullable org_id FK → organization.id (+
    index), backfilled from each row's owner's personal org. user_id retained as
    the acting/created-by column. NOT NULL flip deferred to a later migration.

  identificationattempt is intentionally excluded — it has no user_id owner
  column (it is ground-truth child data of cardgraderesult; RLS reaches it via
  the parent).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4a5b6c7d8e9"
down_revision: Union[str, None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLES: tuple[str, ...] = (
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


def _ix(table: str) -> str:
    return f"ix_{table}_org_id"


def _fk(table: str) -> str:
    return f"fk_{table}_org_id_organization"


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("org_id", sa.Integer(), nullable=True))
        op.create_index(_ix(table), table, ["org_id"])
        op.create_foreign_key(_fk(table), table, "organization", ["org_id"], ["id"])

    # Backfill from each row's owner (user_id) → that user's personal org-of-one
    # (created in d2e3f4a5b6c7). Deterministic: one personal owner-membership/user.
    bind = op.get_bind()
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


def downgrade() -> None:
    for table in _TABLES:
        op.drop_constraint(_fk(table), table, type_="foreignkey")
        op.drop_index(_ix(table), table_name=table)
        op.drop_column(table, "org_id")
