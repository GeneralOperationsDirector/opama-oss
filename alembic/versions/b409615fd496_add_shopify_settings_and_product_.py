"""add shopify settings and product mapping tables

Revision ID: b409615fd496
Revises: 86fa4bee763f
Create Date: 2026-06-13

Changes:
  - New table: shopifysettings (per-user Shopify store config)
  - New table: shopifyproductmapping (catalog entry -> Shopify product id)

Both tables belong to the optional `shopify` external plugin
(external_plugins/opama_shopify/) but are created unconditionally, like the
other premium-plugin tables, since alembic manages the full schema regardless
of ENABLED_PLUGINS (see app/plugin_loader.py / load_plugin_models()).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b409615fd496'
down_revision: Union[str, None] = '86fa4bee763f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'shopifysettings',
        sa.Column('id',                sa.Integer(),  nullable=False),
        sa.Column('user_id',           sa.Integer(),  nullable=False),
        sa.Column('shop_domain',       sa.String(),   nullable=False, server_default=''),
        sa.Column('access_token',      sa.String(),   nullable=True),
        sa.Column('last_published_at', sa.String(),   nullable=True),
        sa.Column('created_at',        sa.String(),   nullable=False),
        sa.Column('updated_at',        sa.String(),   nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_shopifysettings_user_id', 'shopifysettings', ['user_id'], unique=True)

    op.create_table(
        'shopifyproductmapping',
        sa.Column('id',                  sa.Integer(), nullable=False),
        sa.Column('user_id',              sa.Integer(), nullable=False),
        sa.Column('catalog_id',           sa.String(),  nullable=False),
        sa.Column('shopify_product_id',   sa.String(),  nullable=False),
        sa.Column('updated_at',           sa.String(),  nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'catalog_id', name='uq_shopify_mapping_user_catalog'),
    )
    op.create_index('ix_shopifyproductmapping_user_id', 'shopifyproductmapping', ['user_id'])
    op.create_index('ix_shopifyproductmapping_catalog_id', 'shopifyproductmapping', ['catalog_id'])


def downgrade() -> None:
    op.drop_index('ix_shopifyproductmapping_catalog_id', table_name='shopifyproductmapping')
    op.drop_index('ix_shopifyproductmapping_user_id', table_name='shopifyproductmapping')
    op.drop_table('shopifyproductmapping')

    op.drop_index('ix_shopifysettings_user_id', table_name='shopifysettings')
    op.drop_table('shopifysettings')
