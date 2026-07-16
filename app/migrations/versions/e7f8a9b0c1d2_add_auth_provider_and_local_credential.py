# app/alembic/versions/e7f8a9b0c1d2_add_auth_provider_and_local_credential.py
"""add auth_provider column and localcredential table

Revision ID: e7f8a9b0c1d2
Revises: f1a2b3c4d5e6
Create Date: 2026-06-07

Adds support for the "local" auth provider (username/password accounts for
self-hosted instances) alongside the existing Firebase-backed accounts:
- user.auth_provider: which provider owns the account ("firebase" | "local")
- user.firebase_uid: relaxed to nullable (local accounts have none; Postgres
  unique indexes treat NULLs as distinct, so the existing unique index still
  enforces uniqueness for Firebase-backed rows)
- localcredential: one row per local-auth user (username, optional password).
  Table name has no underscore to match this codebase's SQLModel convention
  (see genericasset, inventoryitem, cardgraderesult — SQLModel derives table
  names as cls.__name__.lower(), and LocalCredential follows that here too).
"""
from alembic import op
import sqlalchemy as sa

revision = "e7f8a9b0c1d2"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column("auth_provider", sa.String(), nullable=False, server_default="firebase"),
    )
    op.alter_column("user", "firebase_uid", existing_type=sa.String(), nullable=True)

    op.create_table(
        "localcredential",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=True),
        sa.Column("password_set_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        op.f("ix_localcredential_user_id"), "localcredential", ["user_id"], unique=True
    )
    op.create_index(
        op.f("ix_localcredential_username"), "localcredential", ["username"], unique=True
    )
    op.create_foreign_key(
        "fk_localcredential_user_id",
        "localcredential",
        "user",
        ["user_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_localcredential_user_id", "localcredential", type_="foreignkey")
    op.drop_index(op.f("ix_localcredential_username"), table_name="localcredential")
    op.drop_index(op.f("ix_localcredential_user_id"), table_name="localcredential")
    op.drop_table("localcredential")

    op.alter_column("user", "firebase_uid", existing_type=sa.String(), nullable=False)
    op.drop_column("user", "auth_provider")
