"""drop_pokemon_tcg_fks_from_cardgraderesult

Revision ID: 08861d51264f
Revises: b2c3d4e5f6a7
Create Date: 2026-06-13 14:43:44.289421

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '08861d51264f'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # card/inventoryitem live in the optional opama_pokemon_tcg external plugin
    # and may not exist in this deployment's schema (e.g. core-only installs) —
    # cardgraderesult.card_id/inventory_item_id become soft references.
    op.drop_constraint("cardgraderesult_card_id_fkey", "cardgraderesult", type_="foreignkey")
    op.drop_constraint("cardgraderesult_inventory_item_id_fkey", "cardgraderesult", type_="foreignkey")
    op.create_index(
        op.f("ix_cardgraderesult_inventory_item_id"),
        "cardgraderesult",
        ["inventory_item_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_cardgraderesult_inventory_item_id"), table_name="cardgraderesult")
    op.create_foreign_key(
        "cardgraderesult_inventory_item_id_fkey",
        "cardgraderesult", "inventoryitem",
        ["inventory_item_id"], ["id"],
    )
    op.create_foreign_key(
        "cardgraderesult_card_id_fkey",
        "cardgraderesult", "card",
        ["card_id"], ["id"],
    )
