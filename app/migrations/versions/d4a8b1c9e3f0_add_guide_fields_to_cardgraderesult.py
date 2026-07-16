"""add guide_outer and guide_inner to cardgraderesult

Revision ID: d4a8b1c9e3f0
Revises: c7e4f1a8b2d0
Create Date: 2026-05-03

Stores the raw "x,y,w,h" guide strings from the user's annotation canvas so
that the debug-view endpoint can replay the guided rectification and centering
rather than falling back to auto-detection.
"""

from alembic import op
import sqlalchemy as sa

revision = "d4a8b1c9e3f0"
down_revision = "c7e4f1a8b2d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cardgraderesult", sa.Column("guide_outer", sa.String(), nullable=True))
    op.add_column("cardgraderesult", sa.Column("guide_inner", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("cardgraderesult", "guide_outer")
    op.drop_column("cardgraderesult", "guide_inner")
