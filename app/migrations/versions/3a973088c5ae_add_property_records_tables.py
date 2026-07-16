"""add property records tables

Revision ID: 3a973088c5ae
Revises: 9793d6bc9e19
Create Date: 2026-06-14

Changes:
  - New tables for the Property Records module
    (services/real_estate/models.py):
      - mortgageloan — a mortgage/loan against a property (lender, terms,
        user-maintained current balance, document). FK to customasset.id.
      - propertyvaluation — a point-in-time valuation (appraisal, market
        estimate, tax assessment, document). FK to customasset.id.
      - propertytaxrecord — a property tax bill for a given tax year, with
        an optional due date and paid flag. FK to customasset.id.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3a973088c5ae'
down_revision: Union[str, None] = '9793d6bc9e19'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'mortgageloan',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('lender', sa.String(), nullable=False),
        sa.Column('loan_number', sa.String(), nullable=True),
        sa.Column('original_amount', sa.Float(), nullable=True),
        sa.Column('interest_rate', sa.Float(), nullable=True),
        sa.Column('term_months', sa.Integer(), nullable=True),
        sa.Column('monthly_payment', sa.Float(), nullable=True),
        sa.Column('start_date', sa.String(), nullable=True),
        sa.Column('current_balance', sa.Float(), nullable=True),
        sa.Column('document_url', sa.String(), nullable=True),
        sa.Column('document_filename', sa.String(), nullable=True),
        sa.Column('notes', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['asset_id'], ['customasset.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_mortgageloan_user_id', 'mortgageloan', ['user_id'])
    op.create_index('ix_mortgageloan_asset_id', 'mortgageloan', ['asset_id'])

    op.create_table(
        'propertyvaluation',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('valuation_amount', sa.Float(), nullable=False),
        sa.Column('valuation_date', sa.String(), nullable=True),
        sa.Column('source', sa.String(), nullable=True),
        sa.Column('document_url', sa.String(), nullable=True),
        sa.Column('document_filename', sa.String(), nullable=True),
        sa.Column('notes', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['asset_id'], ['customasset.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_propertyvaluation_user_id', 'propertyvaluation', ['user_id'])
    op.create_index('ix_propertyvaluation_asset_id', 'propertyvaluation', ['asset_id'])

    op.create_table(
        'propertytaxrecord',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('tax_year', sa.Integer(), nullable=False),
        sa.Column('assessed_value', sa.Float(), nullable=True),
        sa.Column('tax_amount', sa.Float(), nullable=True),
        sa.Column('due_date', sa.String(), nullable=True),
        sa.Column('paid', sa.Boolean(), nullable=False),
        sa.Column('document_url', sa.String(), nullable=True),
        sa.Column('document_filename', sa.String(), nullable=True),
        sa.Column('notes', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['asset_id'], ['customasset.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_propertytaxrecord_user_id', 'propertytaxrecord', ['user_id'])
    op.create_index('ix_propertytaxrecord_asset_id', 'propertytaxrecord', ['asset_id'])


def downgrade() -> None:
    op.drop_index('ix_propertytaxrecord_asset_id', table_name='propertytaxrecord')
    op.drop_index('ix_propertytaxrecord_user_id', table_name='propertytaxrecord')
    op.drop_table('propertytaxrecord')

    op.drop_index('ix_propertyvaluation_asset_id', table_name='propertyvaluation')
    op.drop_index('ix_propertyvaluation_user_id', table_name='propertyvaluation')
    op.drop_table('propertyvaluation')

    op.drop_index('ix_mortgageloan_asset_id', table_name='mortgageloan')
    op.drop_index('ix_mortgageloan_user_id', table_name='mortgageloan')
    op.drop_table('mortgageloan')
