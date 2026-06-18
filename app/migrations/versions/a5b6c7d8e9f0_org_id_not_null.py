"""flip org_id NOT NULL on every user-scoped table (pool tenancy)

Revision ID: a5b6c7d8e9f0
Revises: f4a5b6c7d8e9
Create Date: 2026-06-17

Changes (see the pool_vs_silo design memory):
  - Completes the org_id rollout: org_id was added nullable + backfilled in
    e3f4a5b6c7d8 (vertical) and f4a5b6c7d8e9 (general-PAM). The router/write
    layer now sets org_id on every insert, so the tenancy scope key can become
    a hard NOT NULL invariant across all 23 user-scoped tables.
  - This is the prerequisite for the RLS rollout: a nullable org_id would be a
    policy hole (a NULL row escapes every `org_id = current_org` policy).

  Before flipping we do two things:
    1. Purge "deleted-user orphans": rows whose user_id points at a user row
       that no longer exists (a delete with no FK cascade left them behind).
       These can never be backfilled — there is no user, so there is no
       personal org to map to — and nobody can authenticate as the dead user,
       so they are unreachable garbage rather than a tenancy hole. We delete
       them FK-safe (children before parents) so they stop blocking the flip.
       Rows with a NULL user_id are deliberately *not* touched here.
    2. Re-run the owner→personal-org backfill as an idempotent safety net
       (covers any rows written between the add-column migration and this one
       in an environment that wasn't fully caught up).

  If any row still has a NULL org_id after that — e.g. a genuinely NULL user_id
  with no owner at all — the ALTER fails loudly, which is the desired behavior:
  better a blocked migration than a silent tenancy hole.

  identificationattempt is intentionally excluded — it has no user_id/org_id
  owner column (ground-truth child data of cardgraderesult; RLS reaches it via
  the parent).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a5b6c7d8e9f0"
down_revision: Union[str, None] = "f4a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Every user-scoped table that carries org_id, across both add-column batches
# (e3f4a5b6c7d8 + f4a5b6c7d8e9). Order is irrelevant for the flip.
_TABLES: tuple[str, ...] = (
    # vertical batch (e3f4a5b6c7d8)
    "customasset",
    "genericasset",
    "showcase",
    "inventoryitem",
    "deck",
    "wishlist",
    "trade_items",
    "storefrontsettings",
    "saletransaction",
    # general-PAM batch (f4a5b6c7d8e9)
    "insurancepolicy",
    "appraisal",
    "policyitem",
    "mortgageloan",
    "propertyvaluation",
    "propertytaxrecord",
    "servicerecord",
    "vehicledocument",
    "shopifysettings",
    "shopifyproductmapping",
    "cardgraderesult",
    "gradefeedback",
    "portfoliosnapshot",
    "userportfoliosettings",
)


# Orphan predicate: a row whose user_id is set but references a user that no
# longer exists. NULL user_id is intentionally excluded so it still trips the
# loud NOT NULL failure below.
_ORPHAN_WHERE = (
    'user_id IS NOT NULL '
    'AND NOT EXISTS (SELECT 1 FROM "user" u WHERE u.id = t.user_id)'
)

# Non-user-scoped child tables (no user_id of their own): purged via their
# parent being an orphan. (child_table, fk_column, parent_table).
_ORPHAN_CHILDREN: tuple[tuple[str, str, str], ...] = (
    ("deckcard", "deck_id", "deck"),
    ("showcasecard", "showcase_id", "showcase"),
    ("identificationattempt", "result_id", "cardgraderesult"),
    ("customassetfield", "asset_id", "customasset"),
)

# User-scoped tables in FK-safe delete order: every table appears before any
# table it has a foreign key onto (children first, parents last).
_ORPHAN_DELETE_ORDER: tuple[str, ...] = (
    "gradefeedback",       # -> cardgraderesult
    "policyitem",          # -> appraisal, insurancepolicy, customasset
    "cardgraderesult",     # -> customasset
    "appraisal",           # -> customasset
    "mortgageloan",        # -> customasset
    "propertytaxrecord",   # -> customasset
    "propertyvaluation",   # -> customasset
    "servicerecord",       # -> customasset
    "vehicledocument",     # -> customasset
    "insurancepolicy",
    "customasset",
    "deck",
    "showcase",
    # remaining tables carry no inbound FK from within this set; order free
    "genericasset",
    "inventoryitem",
    "wishlist",
    "trade_items",
    "storefrontsettings",
    "saletransaction",
    "shopifysettings",
    "shopifyproductmapping",
    "portfoliosnapshot",
    "userportfoliosettings",
)


def _delete_orphans(bind) -> None:
    """Remove rows owned by a user that no longer exists, children first."""
    # 1. Non-user-scoped children: delete where their parent is an orphan.
    for child, fk_col, parent in _ORPHAN_CHILDREN:
        bind.execute(
            sa.text(
                f"""
                DELETE FROM {child}
                WHERE {fk_col} IN (
                    SELECT id FROM {parent} AS t WHERE {_ORPHAN_WHERE}
                )
                """
            )
        )

    # 2. User-scoped tables, FK-safe order (children before parents).
    for table in _ORPHAN_DELETE_ORDER:
        bind.execute(sa.text(f"DELETE FROM {table} AS t WHERE {_ORPHAN_WHERE}"))


def upgrade() -> None:
    bind = op.get_bind()

    # Purge deleted-user orphans so they don't block the NOT NULL flip.
    _delete_orphans(bind)

    # Idempotent safety-net backfill: map any still-NULL row's owner (user_id) to
    # that user's personal org-of-one (created in d2e3f4a5b6c7). A no-op when the
    # add-column migrations already backfilled everything.
    for table in _TABLES:
        bind.execute(
            sa.text(
                f"""
                UPDATE {table} AS t
                SET org_id = m.org_id
                FROM membership m
                JOIN organization o
                    ON o.id = m.org_id AND o.is_personal = true
                WHERE m.user_id = t.user_id
                  AND t.org_id IS NULL
                """
            )
        )

    # Flip NOT NULL. Fails loudly if any row still has a NULL org_id (orphaned
    # owner) — that is a data-integrity stop, not something to paper over.
    for table in _TABLES:
        op.alter_column(table, "org_id", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    for table in _TABLES:
        op.alter_column(table, "org_id", existing_type=sa.Integer(), nullable=True)
