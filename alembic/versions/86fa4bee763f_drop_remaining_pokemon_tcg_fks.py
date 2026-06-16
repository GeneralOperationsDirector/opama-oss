"""drop_remaining_pokemon_tcg_fks

Revision ID: 86fa4bee763f
Revises: 08861d51264f
Create Date: 2026-06-13 14:45:10.729043

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '86fa4bee763f'
down_revision: Union[str, None] = '08861d51264f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # card/inventoryitem live in the optional opama_pokemon_tcg external plugin
    # and may not exist in this deployment's schema (e.g. core-only installs) —
    # these become soft references (no DB-level FK).
    op.drop_constraint("marketprice_card_id_fkey", "marketprice", type_="foreignkey")
    op.drop_constraint("saletransaction_card_id_fkey", "saletransaction", type_="foreignkey")
    op.drop_constraint("saletransaction_inventory_item_id_fkey", "saletransaction", type_="foreignkey")
    op.drop_constraint("showcasecard_card_id_fkey", "showcasecard", type_="foreignkey")
    op.create_index(
        op.f("ix_saletransaction_inventory_item_id"),
        "saletransaction",
        ["inventory_item_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_saletransaction_inventory_item_id"), table_name="saletransaction")
    op.create_foreign_key(
        "showcasecard_card_id_fkey",
        "showcasecard", "card",
        ["card_id"], ["id"],
    )
    op.create_foreign_key(
        "saletransaction_inventory_item_id_fkey",
        "saletransaction", "inventoryitem",
        ["inventory_item_id"], ["id"],
    )
    op.create_foreign_key(
        "saletransaction_card_id_fkey",
        "saletransaction", "card",
        ["card_id"], ["id"],
    )
    op.create_foreign_key(
        "marketprice_card_id_fkey",
        "marketprice", "card",
        ["card_id"], ["id"],
    )
