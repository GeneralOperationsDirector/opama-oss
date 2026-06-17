"""add organization and membership tables

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-06-17

Changes:
  - New table `organization` — the billing + data-ownership boundary for the
    shared-DB "pool" SaaS tier (see the pool_vs_silo design memory). Holds the
    entitlement (plan_tier / plan_modules / plan_status / current_period_end)
    flipped by the SaaS Stripe webhook and read per-request.
  - New table `membership` — links a User to an Organization with a role
    (owner | manager | staff); unique per (org_id, user_id).
  - Data backfill: every existing user gets an auto-created "org-of-one"
    (is_personal=true) and an owner Membership, so the same org-scoped code
    path serves solo collectors and multi-staff stores uniformly. Slug is
    `user-<id>` (deterministic + guaranteed unique); follow-up migrations add
    `org_id` to the collection tables and point ownership at it.
"""

from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organization",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("plan_tier", sa.String(), nullable=False, server_default="free"),
        sa.Column("plan_modules", sa.String(), nullable=False, server_default="*"),
        sa.Column("plan_status", sa.String(), nullable=False, server_default="active"),
        sa.Column("stripe_customer_id", sa.String(), nullable=True),
        sa.Column("current_period_end", sa.DateTime(), nullable=True),
        sa.Column("is_personal", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_organization_slug", "organization", ["slug"], unique=True)
    op.create_index(
        "ix_organization_stripe_customer_id",
        "organization",
        ["stripe_customer_id"],
        unique=True,
    )

    op.create_table(
        "membership",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("org_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False, server_default="owner"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organization.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "user_id", name="uq_membership_org_user"),
    )
    op.create_index("ix_membership_org_id", "membership", ["org_id"])
    op.create_index("ix_membership_user_id", "membership", ["user_id"])

    _backfill_personal_orgs()


def _backfill_personal_orgs() -> None:
    """Create an org-of-one + owner membership for every pre-existing user."""
    bind = op.get_bind()
    users = bind.execute(
        sa.text("SELECT id, email, display_name, nickname FROM \"user\" ORDER BY id")
    ).fetchall()

    now = datetime.utcnow()
    for user in users:
        user_id = user[0]
        email = user[1]
        display_name = user[2] or user[3]
        name = display_name or (email.split("@")[0] if email else None) or f"Collection {user_id}"

        org_id = bind.execute(
            sa.text(
                """
                INSERT INTO organization
                    (name, slug, plan_tier, plan_modules, plan_status,
                     is_personal, created_at)
                VALUES
                    (:name, :slug, 'free', '*', 'active', true, :created_at)
                RETURNING id
                """
            ),
            {"name": name, "slug": f"user-{user_id}", "created_at": now},
        ).scalar_one()

        bind.execute(
            sa.text(
                """
                INSERT INTO membership (org_id, user_id, role, created_at)
                VALUES (:org_id, :user_id, 'owner', :created_at)
                """
            ),
            {"org_id": org_id, "user_id": user_id, "created_at": now},
        )


def downgrade() -> None:
    op.drop_index("ix_membership_user_id", table_name="membership")
    op.drop_index("ix_membership_org_id", table_name="membership")
    op.drop_table("membership")
    op.drop_index("ix_organization_stripe_customer_id", table_name="organization")
    op.drop_index("ix_organization_slug", table_name="organization")
    op.drop_table("organization")
