"""add plugin_data table

Revision ID: 60959477722e
Revises: b409615fd496
Create Date: 2026-06-13

Changes:
  - New table: plugin_data — generic per-(plugin_id, entity_type, entity_id)
    JSON blob storage. See services/shared/models_plugin_data.py and
    services/shared/plugin_data.py.

This is the core, always-loaded table that backs the additive
DB-extensibility channel described in docs/MODULE_DEVELOPMENT.md §4(A) —
modules (including dynamic/pip installs that can't declare their own
tables) persist settings and per-entity extension fields here instead of
defining a new table + migration.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '60959477722e'
down_revision: Union[str, None] = 'b409615fd496'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'plugin_data',
        sa.Column('id',          sa.Integer(),  nullable=False),
        sa.Column('plugin_id',   sa.String(),   nullable=False),
        sa.Column('entity_type', sa.String(),   nullable=False),
        sa.Column('entity_id',   sa.Integer(),  nullable=False, server_default='0'),
        sa.Column('data',        sa.JSON(),     nullable=False),
        sa.Column('updated_at',  sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('plugin_id', 'entity_type', 'entity_id', name='uq_plugin_data_scope'),
    )
    op.create_index('ix_plugin_data_plugin_id', 'plugin_data', ['plugin_id'])
    op.create_index('ix_plugin_data_entity_type', 'plugin_data', ['entity_type'])
    op.create_index('ix_plugin_data_entity_id', 'plugin_data', ['entity_id'])


def downgrade() -> None:
    op.drop_index('ix_plugin_data_entity_id', table_name='plugin_data')
    op.drop_index('ix_plugin_data_entity_type', table_name='plugin_data')
    op.drop_index('ix_plugin_data_plugin_id', table_name='plugin_data')
    op.drop_table('plugin_data')
