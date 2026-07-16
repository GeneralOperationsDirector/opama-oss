"""add local-install columns to dynamic_plugins

Revision ID: b2c3d4e5f6a7
Revises: e7f8a9b0c1d2
Create Date: 2026-06-08

Adds the columns needed for type=local plugin installs (download-and-run
in-process, as opposed to type=remote's hosted-proxy model): download_url,
install_path, router_module, router_attr, model_modules_json. All are
nullable=False with server_default="" so existing type=remote rows backfill
cleanly without needing values for fields that don't apply to them (mirrors
the is_admin / server_default=sa.false() precedent in f1a2b3c4d5e6).

router_attr defaults to "router" — the v1 contract requires every
dynamically-installed local plugin to expose an `APIRouter` under that name.
model_modules_json defaults to "[]" — see app/plugin_installer.py for why
local installs are restricted to zero DB models in v1 (import-ordering +
Alembic-managed-schema constraints, documented near load_plugin_models()).

The existing `version` column is reused as "currently-installed version" for
local rows — no parallel `installed_version` column is added.
"""

from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a7"
down_revision = "bb2cc3dd4ee5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dynamic_plugins",
        sa.Column("download_url", sa.String(), nullable=False, server_default=""),
    )
    op.add_column(
        "dynamic_plugins",
        sa.Column("install_path", sa.String(), nullable=False, server_default=""),
    )
    op.add_column(
        "dynamic_plugins",
        sa.Column("router_module", sa.String(), nullable=False, server_default=""),
    )
    op.add_column(
        "dynamic_plugins",
        sa.Column("router_attr", sa.String(), nullable=False, server_default="router"),
    )
    op.add_column(
        "dynamic_plugins",
        sa.Column("model_modules_json", sa.String(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("dynamic_plugins", "model_modules_json")
    op.drop_column("dynamic_plugins", "router_attr")
    op.drop_column("dynamic_plugins", "router_module")
    op.drop_column("dynamic_plugins", "install_path")
    op.drop_column("dynamic_plugins", "download_url")
