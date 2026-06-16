"""extract github publish settings into plugin_data/user_secret

Revision ID: 080d3a246ef0
Revises: 3a973088c5ae
Create Date: 2026-06-14

GitHub publishing moves out of StorefrontSettings into its own
`github_publish` module (services/github_publish/), which stores its
per-user config via the generic plugin_data table and the PAT via
user_secret (service "github_publish_token") — see
docs/MODULE_DEVELOPMENT.md §4(A).

Data-migrates any existing storefrontsettings.github_* values into
plugin_data/user_secret, then drops the four github_* columns. The
existing encrypted token is copied as-is into user_secret.encrypted_value
— both columns use the same app.secrets AES-GCM scheme, so no
decrypt/re-encrypt round trip is needed.
"""

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy import table, column


revision = '080d3a246ef0'
down_revision = '3a973088c5ae'
branch_labels = None
depends_on = None


storefrontsettings = table(
    'storefrontsettings',
    column('user_id', sa.Integer),
    column('github_token', sa.String),
    column('github_repo', sa.String),
    column('github_file_path', sa.String),
    column('github_commit_message', sa.String),
)

plugin_data = table(
    'plugin_data',
    column('plugin_id', sa.String),
    column('entity_type', sa.String),
    column('entity_id', sa.Integer),
    column('data', sa.JSON),
    column('updated_at', sa.DateTime),
)

user_secret = table(
    'user_secret',
    column('user_id', sa.Integer),
    column('service', sa.String),
    column('encrypted_value', sa.String),
    column('hint', sa.String),
    column('created_at', sa.DateTime),
    column('updated_at', sa.DateTime),
)


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(timezone.utc)

    rows = bind.execute(
        sa.select(
            storefrontsettings.c.user_id,
            storefrontsettings.c.github_token,
            storefrontsettings.c.github_repo,
            storefrontsettings.c.github_file_path,
            storefrontsettings.c.github_commit_message,
        ).where(
            sa.or_(
                storefrontsettings.c.github_token.isnot(None),
                storefrontsettings.c.github_repo.isnot(None),
                storefrontsettings.c.github_file_path.isnot(None),
                storefrontsettings.c.github_commit_message.isnot(None),
            )
        )
    ).fetchall()

    for row in rows:
        data = {}
        if row.github_repo:
            data["repo"] = row.github_repo
        if row.github_file_path:
            data["file_path"] = row.github_file_path
        if row.github_commit_message:
            data["commit_message"] = row.github_commit_message

        if data:
            bind.execute(
                plugin_data.insert().values(
                    plugin_id="github_publish",
                    entity_type="user",
                    entity_id=row.user_id,
                    data=data,
                    updated_at=now,
                )
            )

        if row.github_token:
            from app.secrets import decrypt_secret_safe, secret_hint

            bind.execute(
                user_secret.insert().values(
                    user_id=row.user_id,
                    service="github_publish_token",
                    encrypted_value=row.github_token,
                    hint=secret_hint(decrypt_secret_safe(row.github_token)),
                    created_at=now,
                    updated_at=now,
                )
            )

    op.drop_column('storefrontsettings', 'github_token')
    op.drop_column('storefrontsettings', 'github_repo')
    op.drop_column('storefrontsettings', 'github_file_path')
    op.drop_column('storefrontsettings', 'github_commit_message')


def downgrade() -> None:
    op.add_column('storefrontsettings', sa.Column('github_token', sa.String(), nullable=True))
    op.add_column('storefrontsettings', sa.Column('github_repo', sa.String(), nullable=True))
    op.add_column('storefrontsettings', sa.Column('github_file_path', sa.String(), nullable=True))
    op.add_column('storefrontsettings', sa.Column('github_commit_message', sa.String(), nullable=True))

    bind = op.get_bind()

    pd_rows = bind.execute(
        sa.select(plugin_data.c.entity_id, plugin_data.c.data).where(
            plugin_data.c.plugin_id == "github_publish",
            plugin_data.c.entity_type == "user",
        )
    ).fetchall()

    us_rows = bind.execute(
        sa.select(user_secret.c.user_id, user_secret.c.encrypted_value).where(
            user_secret.c.service == "github_publish_token",
        )
    ).fetchall()
    tokens = {r.user_id: r.encrypted_value for r in us_rows}

    pd_user_ids = set()
    for row in pd_rows:
        data = row.data or {}
        values = {}
        if "repo" in data:
            values["github_repo"] = data["repo"]
        if "file_path" in data:
            values["github_file_path"] = data["file_path"]
        if "commit_message" in data:
            values["github_commit_message"] = data["commit_message"]
        if row.entity_id in tokens:
            values["github_token"] = tokens[row.entity_id]

        if values:
            bind.execute(
                storefrontsettings.update()
                .where(storefrontsettings.c.user_id == row.entity_id)
                .values(**values)
            )
        pd_user_ids.add(row.entity_id)

    # Users with a saved token but no other plugin_data fields
    for user_id, encrypted_value in tokens.items():
        if user_id not in pd_user_ids:
            bind.execute(
                storefrontsettings.update()
                .where(storefrontsettings.c.user_id == user_id)
                .values(github_token=encrypted_value)
            )
