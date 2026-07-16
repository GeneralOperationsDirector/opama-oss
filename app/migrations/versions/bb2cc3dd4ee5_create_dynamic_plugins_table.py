"""create dynamic_plugins table

Revision ID: bb2cc3dd4ee5
Revises: e7f8a9b0c1d2
Create Date: 2026-06-16

The dynamic_plugins table is owned by services/plugin_store/models.py. It was
previously created by SQLModel.metadata.create_all() at startup, leaving no
Alembic record. This migration inserts it into the chain so that fresh
installs running only migrations get the complete schema.

Only the base columns are created here; the type=local columns (download_url,
install_path, router_module, router_attr, model_modules_json) are added by the
next migration b2c3d4e5f6a7.
"""
from alembic import op
import sqlalchemy as sa

revision = "bb2cc3dd4ee5"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dynamic_plugins",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plugin_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
        sa.Column("type", sa.String(), nullable=False, server_default="remote"),
        sa.Column("tier", sa.String(), nullable=False, server_default="free"),
        sa.Column("icon", sa.String(), nullable=False, server_default=""),
        sa.Column("version", sa.String(), nullable=False, server_default="1.0.0"),
        sa.Column("remote_url", sa.String(), nullable=False, server_default=""),
        sa.Column("auth_type", sa.String(), nullable=False, server_default="none"),
        sa.Column("api_prefix", sa.String(), nullable=False, server_default=""),
        sa.Column("tags_json", sa.String(), nullable=False, server_default="[]"),
        sa.Column("scopes_json", sa.String(), nullable=False, server_default="[]"),
        sa.Column("manifest_url", sa.String(), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("installed_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plugin_id"),
    )
    op.create_index("ix_dynamic_plugins_plugin_id", "dynamic_plugins", ["plugin_id"])


def downgrade() -> None:
    op.drop_index("ix_dynamic_plugins_plugin_id", table_name="dynamic_plugins")
    op.drop_table("dynamic_plugins")
