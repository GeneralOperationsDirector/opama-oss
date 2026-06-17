"""
Inventory models — a user's owned Pokémon TCG cards.

Owned by the `inventory` plugin (premium tier). Moved out of
services/shared/models.py so the inventory plugin can be disabled/removed
without dragging premium tables into the core schema.
"""

from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field

# ---------------------------------------------------------------------------
# Users & Inventory
# ---------------------------------------------------------------------------


class InventoryItem(SQLModel, table=True):
    """
    A user's ownership of a card (with quantity and condition).

    Attributes:
        user_id: Owner (foreign key to User).
        card_id: Card reference (foreign key to Card).
        quantity: How many copies are owned.
        condition/flags: Condition (Near Mint, etc.) and variant flags.
        grade: Professional grading score (1-10, PSA/BGS/CGC).
        grading_company: Grading service (PSA, BGS, CGC, etc.).
        notes: Optional free-text notes.
        acquired_at: Optional datetime of acquisition (UTC).
        acquired_from: Store, trade partner, etc.
        purchase_price_per_card: Price paid per individual card.
        sale_price_per_card: Sale price per card (when sold).
        sale_date: When the card was sold.
        sale_platform: Where it was sold (eBay, TCGPlayer, etc.).
        currency: ISO-4217 currency code.

    Merge policy:
        Router-level logic merges rows by (user_id, card_id, condition, grade, flags).
        Consider a DB UNIQUE index on those fields to enforce this invariant.
    """

    id: int = Field(default=None, primary_key=True)
    # Ownership/RLS scope (pool tenancy — see pool_vs_silo). user_id kept as the
    # acting/created-by user; nullable through the backfill migration.
    org_id: int = Field(foreign_key="organization.id", index=True)
    user_id: int = Field(foreign_key="user.id")
    card_id: str = Field(foreign_key="card.id")
    quantity: int = Field(default=1)  # TODO(validate): ensure >= 0 at API layer.

    # Card details & condition
    condition: Optional[str] = None  # NM/LP/MP/HP/DMG (for raw/ungraded cards)
    is_holo: Optional[bool] = None
    is_reverse_holo: Optional[bool] = None
    is_alt_art: Optional[bool] = None

    # Professional grading
    grade: Optional[int] = None  # 1-10 (PSA/BGS/CGC grade), None for ungraded
    grading_company: Optional[str] = None  # "PSA", "BGS", "CGC", etc.

    # Purchase tracking
    acquired_at: Optional[datetime] = None  # Purchase/acquisition date (UTC)
    acquired_from: Optional[str] = None  # Source: "eBay", "TCGPlayer", "Trade", "Pack Pull"
    purchase_price_per_card: Optional[float] = None  # Price paid per individual card
    currency: Optional[str] = None  # ISO-4217 code (USD, EUR, etc.)

    # Sale tracking (when sold)
    sale_price_per_card: Optional[float] = None  # Sale price per card
    sale_date: Optional[datetime] = None  # When sold (UTC)
    sale_platform: Optional[str] = None  # "eBay", "TCGPlayer", "Local Sale"

    # Notes
    notes: Optional[str] = None

    # TODO(index):
    #   CREATE INDEX ix_inventory_user ON inventoryitem(user_id);
    #   Optional composite index for reporting: (user_id, card_id).
    #   Consider unique index on (user_id, card_id, condition, grade, is_holo, is_reverse_holo, is_alt_art).
