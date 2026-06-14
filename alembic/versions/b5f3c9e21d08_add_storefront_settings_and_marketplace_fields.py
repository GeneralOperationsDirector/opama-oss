"""add storefront settings table and marketplace link fields to customasset

Revision ID: b5f3c9e21d08
Revises: 9c4d1e83a2f7
Create Date: 2026-05-02

Changes:
  - New table: storefrontsettings (per-user shop config)
  - customasset: marketplace_ebay, marketplace_facebook,
                 marketplace_kijiji, marketplace_craigslist
"""

from alembic import op
import sqlalchemy as sa

revision = 'b5f3c9e21d08'
down_revision = '9c4d1e83a2f7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'storefrontsettings',
        sa.Column('id',                sa.Integer(),  nullable=False),
        sa.Column('user_id',           sa.Integer(),  nullable=False),
        sa.Column('site_name',         sa.String(),   nullable=False, server_default='My Shop'),
        sa.Column('site_url',          sa.String(),   nullable=False, server_default=''),
        sa.Column('public_api_url',    sa.String(),   nullable=False, server_default=''),
        sa.Column('catalog_path',      sa.String(),   nullable=True),
        sa.Column('webhook_url',       sa.String(),   nullable=True),
        sa.Column('last_published_at', sa.String(),   nullable=True),
        sa.Column('created_at',        sa.String(),   nullable=False),
        sa.Column('updated_at',        sa.String(),   nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_storefrontsettings_user_id', 'storefrontsettings', ['user_id'], unique=True)

    op.add_column('customasset', sa.Column('marketplace_ebay',       sa.String(), nullable=True))
    op.add_column('customasset', sa.Column('marketplace_facebook',   sa.String(), nullable=True))
    op.add_column('customasset', sa.Column('marketplace_kijiji',     sa.String(), nullable=True))
    op.add_column('customasset', sa.Column('marketplace_craigslist', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('customasset', 'marketplace_craigslist')
    op.drop_column('customasset', 'marketplace_kijiji')
    op.drop_column('customasset', 'marketplace_facebook')
    op.drop_column('customasset', 'marketplace_ebay')
    op.drop_index('ix_storefrontsettings_user_id', table_name='storefrontsettings')
    op.drop_table('storefrontsettings')
