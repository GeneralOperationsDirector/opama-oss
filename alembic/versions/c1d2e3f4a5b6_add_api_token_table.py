"""add api_token table

Revision ID: c1d2e3f4a5b6
Revises: 080d3a246ef0
Create Date: 2026-06-15

Changes:
  - New table api_token (services/shared/models_security.py): personal
    access tokens for external agents (e.g. Claude Code via MCP) to call
    into a user's opama data via the AI Assistant module's MCP endpoint.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, None] = '080d3a246ef0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'api_token',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('token_hash', sa.String(), nullable=False),
        sa.Column('hint', sa.String(), nullable=False),
        sa.Column('scopes', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_api_token_user_id', 'api_token', ['user_id'])
    op.create_index('ix_api_token_token_hash', 'api_token', ['token_hash'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_api_token_token_hash', table_name='api_token')
    op.drop_index('ix_api_token_user_id', table_name='api_token')
    op.drop_table('api_token')
