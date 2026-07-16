"""create grading tables (cardgraderesult, identificationattempt, gradefeedback)

Revision ID: aa1bb2cc3dd4
Revises: 575bf8c48577
Create Date: 2026-06-16

These tables are owned by the opama_grading external plugin. Previously they
were created by SQLModel.metadata.create_all() at startup, which left no
migration record. This migration inserts them into the chain so fresh
installs that run only migrations (e.g. CI) get a complete schema.
"""
from alembic import op
import sqlalchemy as sa

revision = "aa1bb2cc3dd4"
down_revision = "575bf8c48577"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cardgraderesult",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("card_id", sa.String(), nullable=True),
        sa.Column("inventory_item_id", sa.Integer(), nullable=True),
        sa.Column("asset_id", sa.Integer(), nullable=True),
        sa.Column("estimated_grade", sa.Float(), nullable=False),
        sa.Column("grade_label", sa.String(), nullable=False),
        sa.Column("confidence", sa.String(), nullable=False),
        sa.Column("centering_left_pct", sa.Float(), nullable=False),
        sa.Column("centering_right_pct", sa.Float(), nullable=False),
        sa.Column("centering_top_pct", sa.Float(), nullable=False),
        sa.Column("centering_bottom_pct", sa.Float(), nullable=False),
        sa.Column("centering_score", sa.Integer(), nullable=False),
        sa.Column("corner_tl", sa.Float(), nullable=False),
        sa.Column("corner_tr", sa.Float(), nullable=False),
        sa.Column("corner_bl", sa.Float(), nullable=False),
        sa.Column("corner_br", sa.Float(), nullable=False),
        sa.Column("corner_score", sa.Integer(), nullable=False),
        sa.Column("surface_score", sa.Integer(), nullable=False),
        sa.Column("surface_scratch_risk", sa.Float(), nullable=False),
        sa.Column("surface_texture_score", sa.Float(), nullable=True),
        sa.Column("edge_score", sa.Integer(), nullable=False),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("identified_name", sa.String(), nullable=True),
        sa.Column("identified_number", sa.String(), nullable=True),
        sa.Column("identified_set_name", sa.String(), nullable=True),
        sa.Column("identified_catalog_card_id", sa.String(), nullable=True),
        sa.Column("identified_catalog_set_id", sa.String(), nullable=True),
        sa.Column("identification_confidence", sa.String(), nullable=True),
        sa.Column("transferred_to", sa.String(), nullable=True),
        sa.Column("transferred_item_id", sa.Integer(), nullable=True),
        sa.Column("analyzed_at", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["customasset.id"]),
        sa.ForeignKeyConstraint(["card_id"], ["card.id"], name="cardgraderesult_card_id_fkey"),
        sa.ForeignKeyConstraint(["inventory_item_id"], ["inventoryitem.id"], name="cardgraderesult_inventory_item_id_fkey"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cardgraderesult_user_id", "cardgraderesult", ["user_id"])
    op.create_index("ix_cardgraderesult_card_id", "cardgraderesult", ["card_id"])
    # ix_cardgraderesult_inventory_item_id is created by migration 08861d51264f
    # after it drops the FK constraint on this column.

    op.create_table(
        "identificationattempt",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("grade_result_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("extracted_name", sa.String(), nullable=True),
        sa.Column("extracted_number", sa.String(), nullable=True),
        sa.Column("extracted_set", sa.String(), nullable=True),
        sa.Column("actual_name", sa.String(), nullable=True),
        sa.Column("actual_number", sa.String(), nullable=True),
        sa.Column("actual_card_id", sa.String(), nullable=True),
        sa.Column("name_correct", sa.Boolean(), nullable=True),
        sa.Column("number_correct", sa.Boolean(), nullable=True),
        sa.Column("attempted_at", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["grade_result_id"], ["cardgraderesult.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_identificationattempt_grade_result_id", "identificationattempt", ["grade_result_id"])

    op.create_table(
        "gradefeedback",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("grade_result_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("overall_verdict", sa.String(), nullable=False),
        sa.Column("actual_grade", sa.Float(), nullable=True),
        sa.Column("grading_company", sa.String(), nullable=True),
        sa.Column("inaccurate_dimensions", sa.String(), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("submitted_at", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["grade_result_id"], ["cardgraderesult.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_gradefeedback_grade_result_id", "gradefeedback", ["grade_result_id"])
    op.create_index("ix_gradefeedback_user_id", "gradefeedback", ["user_id"])


def downgrade() -> None:
    op.drop_table("gradefeedback")
    op.drop_table("identificationattempt")
    op.drop_table("cardgraderesult")
