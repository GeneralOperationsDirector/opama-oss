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
