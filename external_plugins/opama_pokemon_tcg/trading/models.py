"""
Trading models — wishlist and trade-list entries for Pokémon TCG cards.

Owned by the `trading` plugin (premium tier). Moved out of
services/shared/models_trade.py so the trading plugin can be disabled/removed
without dragging premium tables into the core schema.

Design:
- Each model enforces uniqueness on (user_id, card_id) so a user cannot
  add the same card twice to their wish list or trade list.
- Intended to be joined with Card table for display (see routers/trade_wish.py).

Notes:
- These are simple, minimal models. They intentionally do not store full Card
  data—only foreign keys (card_id) and user-scoped info.
"""

from typing import Optional
from sqlmodel import SQLModel, Field, UniqueConstraint


class WishList(SQLModel, table=True):
    """
    Represents a card that a user wishes to acquire.

    Constraints:
        - (user_id, card_id) must be unique to prevent duplicates.

    Fields:
        id: Auto-increment primary key.
        user_id: Owning user (foreign key to User table, if defined).
        card_id: Desired card (foreign key to Card table, stored as str ID).
        note: Optional freeform note (e.g., preferred condition, trade offer).
    """

    __tablename__ = "wishlist"
    __table_args__ = (
        UniqueConstraint("user_id", "card_id", name="uq_wishlist_user_card"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    # Ownership/RLS scope (pool tenancy — see pool_vs_silo); nullable through backfill.
    org_id: int = Field(foreign_key="organization.id", index=True)
    user_id: int  # TODO: If you want referential integrity, add FK(User.id)
    card_id: str  # TODO: Add FK("card.id") if schema supports it
    note: Optional[str] = None


class TradeItem(SQLModel, table=True):
    """
    Represents a card a user is offering for trade.

    Constraints:
        - (user_id, card_id) must be unique to prevent duplicate trade listings.

    Fields:
        id: Auto-increment primary key.
        user_id: Owning user (foreign key to User table, if defined).
        card_id: Card offered for trade (foreign key to Card table).
        quantity: How many copies the user is offering (default 1).
        condition: Optional freeform string (e.g., "NM", "LP", "Played").
    """

    __tablename__ = "trade_items"
    __table_args__ = (
        UniqueConstraint("user_id", "card_id", name="uq_trade_user_card"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    # Ownership/RLS scope (pool tenancy — see pool_vs_silo); nullable through backfill.
    org_id: int = Field(foreign_key="organization.id", index=True)
    user_id: int
    card_id: str
    quantity: int = 1  # TODO: Consider making non-nullable with min=1 validator
    condition: Optional[str] = None
