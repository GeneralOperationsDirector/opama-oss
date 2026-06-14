"""add github publishing fields to storefrontsettings

Revision ID: c7e4f1a8b2d0
Revises: b5f3c9e21d08
Create Date: 2026-05-02

Adds four columns that enable opama to commit catalog.json directly
to GitHub, triggering an automatic Cloudflare Pages deploy:
  - github_token        : Personal Access Token (contents:write scope)
  - github_repo         : owner/repo slug
  - github_file_path    : path to catalog.json inside the repo
  - github_commit_message : commit message template ({n} = item count)
"""

from alembic import op
import sqlalchemy as sa

revision = 'c7e4f1a8b2d0'
down_revision = 'b5f3c9e21d08'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('storefrontsettings', sa.Column('github_token',          sa.String(), nullable=True))
    op.add_column('storefrontsettings', sa.Column('github_repo',           sa.String(), nullable=True))
    op.add_column('storefrontsettings', sa.Column('github_file_path',      sa.String(), nullable=True))
    op.add_column('storefrontsettings', sa.Column('github_commit_message', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('storefrontsettings', 'github_commit_message')
    op.drop_column('storefrontsettings', 'github_file_path')
    op.drop_column('storefrontsettings', 'github_repo')
    op.drop_column('storefrontsettings', 'github_token')
