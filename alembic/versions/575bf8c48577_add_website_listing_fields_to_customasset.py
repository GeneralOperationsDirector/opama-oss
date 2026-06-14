"""add website listing fields to customasset

Revision ID: 575bf8c48577
Revises: 82e2e9a75cc1
Create Date: 2026-04-28

Adds fields to support an external storefront website integration:
  - listed_on_website   : flag to publish the asset to the website
  - listing_price_cad   : asking price shown on the storefront site
  - shipping_price_cad  : flat shipping charged at checkout
  - website_slug        : catalog.json id (e.g. "1952-mantle-311")
  - sale_price_cad      : recorded by the storefront webhook after Stripe sale
  - sale_date           : ISO date of sale
  - sale_platform       : "website", "ebay", "local", etc.
"""

from alembic import op
import sqlalchemy as sa

revision = '575bf8c48577'
down_revision = '82e2e9a75cc1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('customasset', sa.Column('listed_on_website',  sa.Boolean(),     nullable=False, server_default=sa.false()))
    op.add_column('customasset', sa.Column('listing_price_cad',  sa.Float(),        nullable=True))
    op.add_column('customasset', sa.Column('shipping_price_cad', sa.Float(),        nullable=True))
    op.add_column('customasset', sa.Column('website_slug',       sa.String(),       nullable=True))
    op.add_column('customasset', sa.Column('sale_price_cad',     sa.Float(),        nullable=True))
    op.add_column('customasset', sa.Column('sale_date',          sa.String(),       nullable=True))
    op.add_column('customasset', sa.Column('sale_platform',      sa.String(),       nullable=True))
    op.create_index('ix_customasset_website_slug', 'customasset', ['website_slug'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_customasset_website_slug', table_name='customasset')
    op.drop_column('customasset', 'sale_platform')
    op.drop_column('customasset', 'sale_date')
    op.drop_column('customasset', 'sale_price_cad')
    op.drop_column('customasset', 'website_slug')
    op.drop_column('customasset', 'shipping_price_cad')
    op.drop_column('customasset', 'listing_price_cad')
    op.drop_column('customasset', 'listed_on_website')
