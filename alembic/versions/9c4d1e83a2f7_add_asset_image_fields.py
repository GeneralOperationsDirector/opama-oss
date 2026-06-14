"""add front/back image and thumbnail fields to customasset

Revision ID: 9c4d1e83a2f7
Revises: 40cfbb01575e
Create Date: 2026-05-02

Adds four image-related columns to customasset:
  - image_thumb_url      : 300 px-wide JPEG thumbnail for the front image
  - back_image_url       : full-resolution back cover image
  - back_image_thumb_url : 300 px-wide JPEG thumbnail for the back image
"""

from alembic import op
import sqlalchemy as sa

revision = '9c4d1e83a2f7'
down_revision = '40cfbb01575e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('customasset', sa.Column('image_thumb_url',      sa.String(), nullable=True))
    op.add_column('customasset', sa.Column('back_image_url',       sa.String(), nullable=True))
    op.add_column('customasset', sa.Column('back_image_thumb_url', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('customasset', 'back_image_thumb_url')
    op.drop_column('customasset', 'back_image_url')
    op.drop_column('customasset', 'image_thumb_url')
