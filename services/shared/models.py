# app/models.py
"""
Core database models (SQLModel) shared across all of opama.

These are the only tables that must always exist regardless of which
plugins are enabled:
- User: application accounts (Firebase-backed)
- GenericAsset: the asset-class-agnostic collection item used by the
  open-source "Collections" module

Pokémon-specific tables (Card, Set, Deck, InventoryItem, etc.) live in
their respective premium plugin packages — see services/catalog/models.py,
services/inventory/models.py, services/decks/models.py,
services/trading/models.py, services/portfolio/models.py, and
services/showcase/models.py. They are loaded via each plugin's
`model_modules` manifest entry (see app/plugin_loader.py) so that
disabling/removing a plugin doesn't drag its tables into the core schema.
"""

from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field
from sqlalchemy import UniqueConstraint

# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


class User(SQLModel, table=True):
    """
    Represents an application user.

    Attributes:
        id: Primary key (internal database ID).
        firebase_uid: Firebase Authentication UID. Set for Firebase-backed
            accounts; null for local accounts (see LocalCredential). Postgres
            unique indexes treat NULLs as distinct, so multiple local accounts
            can coexist under one unique index.
        auth_provider: which provider owns this account ("firebase" | "local").
        email: User's email address (unique, from Firebase).
        display_name: Display name or nickname.
        nickname: Legacy field for display nickname (deprecated, use display_name).
        created_at: Timestamp when user was created.
    """

    id: int = Field(default=None, primary_key=True)
    firebase_uid: Optional[str] = Field(default=None, unique=True, index=True)
    auth_provider: str = Field(default="firebase")
    email: Optional[str] = Field(default=None, unique=True, index=True)
    display_name: Optional[str] = None
    nickname: Optional[str] = None  # Legacy field, kept for backward compatibility
    is_admin: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Local auth credentials (for the "local" auth provider — self-hosted default)
# ---------------------------------------------------------------------------


class LocalCredential(SQLModel, table=True):
    """
    Username/password credentials for the local auth provider.

    One row per user with auth_provider="local". password_hash is nullable —
    accounts can be created without a password for frictionless local-only use;
    the frontend nudges (and blocks, once the instance is reachable beyond
    localhost) until one is set. See auth_provider_plan memory for full design.
    """

    id: int = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", unique=True, index=True)
    username: str = Field(unique=True, index=True)
    password_hash: Optional[str] = None
    password_set_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Organizations & Memberships (tenancy + billing boundary for the shared-DB
# "pool" SaaS tier — see the pool_vs_silo design memory)
# ---------------------------------------------------------------------------
#
# An Organization is the unit that *owns* collection data and *holds* the
# subscription/entitlement. It is deliberately the boundary, not the User, so a
# store owner can have staff act on the shop's catalog under one subscription.
# A solo collector is modelled as an "org-of-one" (one Organization with a
# single owner Membership) so the same code path serves individuals and stores.
#
# These tables always exist (core), but they are only *load-bearing* in the
# pooled SaaS deployment. Self-hosted/silo instances get a single auto-created
# org and can otherwise ignore them.

# Membership roles, ordered by privilege. owner > manager > staff.
ORG_ROLE_OWNER = "owner"
ORG_ROLE_MANAGER = "manager"
ORG_ROLE_STAFF = "staff"
ORG_ROLES = (ORG_ROLE_OWNER, ORG_ROLE_MANAGER, ORG_ROLE_STAFF)
# Higher rank = more privilege; used for "at least this role" checks.
ORG_ROLE_RANK = {ORG_ROLE_STAFF: 0, ORG_ROLE_MANAGER: 1, ORG_ROLE_OWNER: 2}


class Organization(SQLModel, table=True):
    """
    A billing + data-ownership boundary.

    Collection-type rows (assets, inventory, decks, storefront settings) are
    owned by an Organization via an ``org_id`` column; the ``User`` that created
    or edited a row is retained separately for the audit trail. Entitlements
    (tier/modules) live here, not on the User, so one subscription covers a
    store's whole staff.

    Attributes:
        id: Primary key.
        name: Human-facing org / shop name.
        slug: URL-safe unique handle (also the storefront/public identifier).
        plan_tier: entitlement tier — one of app.license.TIER_RANK keys
            ("core" | "free" | "premium" | "enterprise"). Flipped by the SaaS
            Stripe webhook; read per-request by the require_tier() dependency.
        plan_modules: allow-list of module ids ("*" = all modules in the tier).
        plan_status: subscription lifecycle ("active" | "past_due" |
            "canceled"). Distinct from tier so a lapse can gate without losing
            which tier they were on.
        stripe_customer_id: Stripe customer this org bills under (nullable for
            self-hosted / un-billed orgs).
        current_period_end: when the current paid period ends (entitlement
            expiry); null for non-expiring/self-hosted orgs.
        is_personal: True for the auto-created org-of-one backing a solo user.
        created_at: creation timestamp.
    """

    id: int = Field(default=None, primary_key=True)
    name: str
    slug: str = Field(unique=True, index=True)
    plan_tier: str = Field(default="free")
    plan_modules: str = Field(default="*")
    plan_status: str = Field(default="active")
    stripe_customer_id: Optional[str] = Field(default=None, unique=True, index=True)
    current_period_end: Optional[datetime] = None
    is_personal: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    # Per-org key for the storefront export endpoints (GET /assets/website-listings,
    # POST /assets/website-listings/{slug}/sold). Scopes the storefront pull + sale
    # webhook to this one org under pool tenancy. Null until the owner generates one.
    export_key: Optional[str] = Field(default=None, unique=True, index=True)
    # Opt-in: when true, this org's trade list / wishlist are visible to the
    # cross-user trade-matching engine (and an RLS discovery-read policy). Off by default.
    trade_discoverable: bool = Field(default=False)


class Membership(SQLModel, table=True):
    """
    Links a User to an Organization with a role.

    A user may belong to several orgs (e.g. their personal collection plus a
    shop they work at); the app resolves an "active org" per request. The
    (org_id, user_id) pair is unique — one membership row per user per org.

    role: one of ORG_ROLES (owner | manager | staff). Ownership/mutation checks
    shift from "row.user_id == current_user.id" to "current_user has a
    sufficient-role Membership in the row's org".
    """

    __table_args__ = (UniqueConstraint("org_id", "user_id", name="uq_membership_org_user"),)

    id: int = Field(default=None, primary_key=True)
    org_id: int = Field(foreign_key="organization.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    role: str = Field(default=ORG_ROLE_OWNER)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Generic Assets (non-card items: books, electronics, collectibles, etc.)
# ---------------------------------------------------------------------------


class GenericAsset(SQLModel, table=True):
    """
    A user-owned asset that is not a Pokémon card.

    asset_class: broad category — "book", "electronics", "clothing",
                  "collectible", "media", "other"
    identifier / identifier_type: e.g. ISBN-13 + "isbn", barcode + "barcode",
                                   serial number + "serial"
    asset_metadata: JSON blob for class-specific fields (author, publisher,
                    model number, etc.) populated by the identify endpoint.
    """

    id: int = Field(default=None, primary_key=True)
    # Ownership/RLS scope (pool tenancy — see pool_vs_silo). org_id owns the row;
    # user_id is kept as the creating/acting user for audit. Nullable through the
    # backfill migration, then becomes the canonical tenancy scope key.
    org_id: int = Field(foreign_key="organization.id", index=True)
    user_id: int = Field(foreign_key="user.id")

    asset_class: str = Field(default="other")  # book / electronics / collectible / …
    name: str

    # Identification
    identifier: Optional[str] = None           # ISBN, barcode, serial, etc.
    identifier_type: Optional[str] = None      # "isbn" | "barcode" | "serial" | "sku"

    # Quantity & condition
    quantity: int = Field(default=1)
    condition: Optional[str] = None            # New / Good / Fair / Poor

    # Purchase tracking
    purchase_price: Optional[float] = None
    currency: Optional[str] = "CAD"
    acquired_from: Optional[str] = None
    acquired_at: Optional[datetime] = None

    # Sale tracking
    sale_price: Optional[float] = None
    sale_date: Optional[datetime] = None
    sale_platform: Optional[str] = None

    # Flexible extra fields (JSON string)
    asset_metadata: Optional[str] = None

    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
