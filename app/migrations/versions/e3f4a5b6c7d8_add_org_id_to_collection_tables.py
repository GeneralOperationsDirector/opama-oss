"""add org_id to collection tables (pool tenancy)

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-06-17

Changes (see the pool_vs_silo design memory):
  - Add a nullable `org_id` FK → organization.id (+ index) to the Pokémon-vertical
    ownership tables: customasset, genericasset, showcase, inventoryitem, deck,
    wishlist, trade_items, storefrontsettings, saletransaction.
  - Backfill org_id from each row's owner: user_id → that user's *personal* org
    (the org-of-one created in d2e3f4a5b6c7). user_id is retained as the
    acting/created-by column for audit; org_id becomes the tenancy/RLS scope.
  - Column stays NULLABLE here. A later migration flips it NOT NULL once the
    router/write layer sets org_id on every insert.

Deferred to a follow-up batch (general-PAM modules, not the Pokémon vertical):
  insurancepolicy, policyitem, mortgageloan, propertytaxrecord, propertyvaluation,
  appraisal, vehicledocument, servicerecord, shopifysettings, shopifyproductmapping,
  cardgraderesult, gradefeedback, identificationattempt, portfoliosnapshot,
  userportfoliosettings.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tables that get an org_id, with the user-id column to backfill from. Every one
# of these currently carries the owner in `user_id`.
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

    # Backfill: map each row's owner (user_id) to that user's personal org-of-one.
    # One personal owner-membership exists per user (from d2e3f4a5b6c7), so this is
    # deterministic. Rows with an orphaned user_id (shouldn't exist) stay NULL.
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
