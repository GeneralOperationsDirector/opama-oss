"""add vehicle maintenance tables

Revision ID: 9793d6bc9e19
Revises: ecebd20cbdce
Create Date: 2026-06-14

Changes:
  - New tables for the Vehicle Maintenance module
    (services/vehicles/models.py):
      - servicerecord — a maintenance/service log entry for a vehicle
        (date, odometer, type, cost, vendor, receipt document). FK to
        customasset.id.
      - vehicledocument — a registration, title, insurance card, or
        inspection document with optional issue/expiry dates. FK to
        customasset.id.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9793d6bc9e19'
down_revision: Union[str, None] = 'ecebd20cbdce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'servicerecord',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('service_date', sa.String(), nullable=True),
        sa.Column('odometer', sa.Integer(), nullable=True),
        sa.Column('service_type', sa.String(), nullable=False),
        sa.Column('cost', sa.Float(), nullable=True),
        sa.Column('vendor', sa.String(), nullable=True),
        sa.Column('notes', sa.String(), nullable=True),
        sa.Column('document_url', sa.String(), nullable=True),
        sa.Column('document_filename', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['asset_id'], ['customasset.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_servicerecord_user_id', 'servicerecord', ['user_id'])
    op.create_index('ix_servicerecord_asset_id', 'servicerecord', ['asset_id'])

    op.create_table(
        'vehicledocument',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('doc_type', sa.String(), nullable=False),
        sa.Column('issued_date', sa.String(), nullable=True),
        sa.Column('expiry_date', sa.String(), nullable=True),
        sa.Column('document_url', sa.String(), nullable=True),
        sa.Column('document_filename', sa.String(), nullable=True),
        sa.Column('notes', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['asset_id'], ['customasset.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_vehicledocument_user_id', 'vehicledocument', ['user_id'])
    op.create_index('ix_vehicledocument_asset_id', 'vehicledocument', ['asset_id'])


def downgrade() -> None:
    op.drop_index('ix_vehicledocument_asset_id', table_name='vehicledocument')
    op.drop_index('ix_vehicledocument_user_id', table_name='vehicledocument')
    op.drop_table('vehicledocument')

    op.drop_index('ix_servicerecord_asset_id', table_name='servicerecord')
    op.drop_index('ix_servicerecord_user_id', table_name='servicerecord')
    op.drop_table('servicerecord')
