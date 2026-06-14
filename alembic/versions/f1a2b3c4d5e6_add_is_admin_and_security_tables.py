"""add is_admin to user, and user_secret / audit_log tables

Revision ID: f1a2b3c4d5e6
Revises: d4a8b1c9e3f0
Create Date: 2026-06-07

Adds the is_admin flag used by services.auth.middleware.require_admin (admin
gate for plugin installs and /debug/db-info), plus the UserSecret vault and
AuditLog tables backing the encrypted-secrets work in app/secrets.py.
"""

from alembic import op
import sqlalchemy as sa

revision = "f1a2b3c4d5e6"
down_revision = "d4a8b1c9e3f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "user_secret",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("service", sa.String(), nullable=False),
        sa.Column("encrypted_value", sa.String(), nullable=False),
        sa.Column("hint", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_user_secret_user_id", "user_secret", ["user_id"])
    op.create_index("ix_user_secret_service", "user_secret", ["service"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("target", sa.String(), nullable=True),
        sa.Column("ip_address", sa.String(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("detail", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_index("ix_user_secret_service", table_name="user_secret")
    op.drop_index("ix_user_secret_user_id", table_name="user_secret")
    op.drop_table("user_secret")
    op.drop_column("user", "is_admin")
