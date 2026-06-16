"""add insurance tables

Revision ID: ecebd20cbdce
Revises: 60959477722e
Create Date: 2026-06-14

Changes:
  - New tables for the Insurance & Appraisals module
    (services/insurance/models.py):
      - insurancepolicy — a user's insurance policy covering their
        collection (provider, policy number, coverage, premium, renewal
        dates, document).
      - appraisal — a standalone or asset-linked appraisal record
        (appraiser, value, date, document). FK to customasset.id.
      - policyitem — itemized "scheduled" coverage linking a policy to a
        specific customasset (or a free-text description) and optionally
        an appraisal. FKs to insurancepolicy.id, customasset.id,
        appraisal.id.

Note: this repo currently has two alembic heads (this migration's parent,
60959477722e_add_plugin_data_table, and
c7e4f1a8b2d0_add_github_fields_to_storefrontsettings) — a pre-existing
divergence unrelated to this change.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'ecebd20cbdce'
down_revision: Union[str, None] = '60959477722e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'insurancepolicy',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(), nullable=False),
        sa.Column('policy_number', sa.String(), nullable=True),
        sa.Column('policy_type', sa.String(), nullable=True),
        sa.Column('coverage_amount', sa.Float(), nullable=True),
        sa.Column('deductible', sa.Float(), nullable=True),
        sa.Column('premium_amount', sa.Float(), nullable=True),
        sa.Column('premium_frequency', sa.String(), nullable=True),
        sa.Column('start_date', sa.String(), nullable=True),
        sa.Column('end_date', sa.String(), nullable=True),
        sa.Column('document_url', sa.String(), nullable=True),
        sa.Column('document_filename', sa.String(), nullable=True),
        sa.Column('notes', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_insurancepolicy_user_id', 'insurancepolicy', ['user_id'])

    op.create_table(
        'appraisal',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=True),
        sa.Column('appraiser_name', sa.String(), nullable=True),
        sa.Column('appraised_value', sa.Float(), nullable=False),
        sa.Column('appraisal_date', sa.String(), nullable=True),
        sa.Column('document_url', sa.String(), nullable=True),
        sa.Column('document_filename', sa.String(), nullable=True),
        sa.Column('notes', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['asset_id'], ['customasset.id']),
    )
    op.create_index('ix_appraisal_user_id', 'appraisal', ['user_id'])
    op.create_index('ix_appraisal_asset_id', 'appraisal', ['asset_id'])

    op.create_table(
        'policyitem',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('policy_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=True),
        sa.Column('appraisal_id', sa.Integer(), nullable=True),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('scheduled_amount', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['policy_id'], ['insurancepolicy.id']),
        sa.ForeignKeyConstraint(['asset_id'], ['customasset.id']),
        sa.ForeignKeyConstraint(['appraisal_id'], ['appraisal.id']),
    )
    op.create_index('ix_policyitem_policy_id', 'policyitem', ['policy_id'])
    op.create_index('ix_policyitem_user_id', 'policyitem', ['user_id'])
    op.create_index('ix_policyitem_asset_id', 'policyitem', ['asset_id'])


def downgrade() -> None:
    op.drop_index('ix_policyitem_asset_id', table_name='policyitem')
    op.drop_index('ix_policyitem_user_id', table_name='policyitem')
    op.drop_index('ix_policyitem_policy_id', table_name='policyitem')
    op.drop_table('policyitem')

    op.drop_index('ix_appraisal_asset_id', table_name='appraisal')
    op.drop_index('ix_appraisal_user_id', table_name='appraisal')
    op.drop_table('appraisal')

    op.drop_index('ix_insurancepolicy_user_id', table_name='insurancepolicy')
    op.drop_table('insurancepolicy')
