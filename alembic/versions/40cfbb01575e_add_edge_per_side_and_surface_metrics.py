"""add_edge_per_side_and_surface_metrics

Revision ID: 40cfbb01575e
Revises: 575bf8c48577
Create Date: 2026-04-30 18:46:08.718079

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '40cfbb01575e'
down_revision: Union[str, None] = '575bf8c48577'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('cardgraderesult', sa.Column('edge_top_std', sa.Float(), nullable=True))
    op.add_column('cardgraderesult', sa.Column('edge_bottom_std', sa.Float(), nullable=True))
    op.add_column('cardgraderesult', sa.Column('edge_left_std', sa.Float(), nullable=True))
    op.add_column('cardgraderesult', sa.Column('edge_right_std', sa.Float(), nullable=True))
    op.add_column('cardgraderesult', sa.Column('surface_symmetry', sa.Float(), nullable=True))
    op.add_column('cardgraderesult', sa.Column('surface_th_h', sa.Float(), nullable=True))
    op.add_column('cardgraderesult', sa.Column('surface_th_v', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('cardgraderesult', 'surface_th_v')
    op.drop_column('cardgraderesult', 'surface_th_h')
    op.drop_column('cardgraderesult', 'surface_symmetry')
    op.drop_column('cardgraderesult', 'edge_right_std')
    op.drop_column('cardgraderesult', 'edge_left_std')
    op.drop_column('cardgraderesult', 'edge_bottom_std')
    op.drop_column('cardgraderesult', 'edge_top_std')
