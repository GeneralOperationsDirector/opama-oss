"""
Deck models — Pokémon TCG deck building.

Owned by the `decks` plugin (premium tier). Moved out of
services/shared/models.py so the decks plugin can be disabled/removed
without dragging premium tables into the core schema.
"""

from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field

# ---------------------------------------------------------------------------
# Decks & DeckCards
# ---------------------------------------------------------------------------


class Deck(SQLModel, table=True):
    """
    Represents a deck created by a user.

    Attributes:
        name: Deck name.
        format: Format label (e.g., Standard, Expanded).
        strategy_notes: Optional notes on deck strategy.
        created_at/updated_at: Timestamps (UTC).
    """

    id: int = Field(default=None, primary_key=True)
    # Ownership/RLS scope (pool tenancy — see pool_vs_silo). user_id kept as the
    # acting/created-by user; nullable through the backfill migration.
    org_id: int = Field(foreign_key="organization.id", index=True)
    user_id: int = Field(foreign_key="user.id")
    name: str
    format: Optional[str] = None
    strategy_notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    # TODO(audit): Consider a trigger or application hook to update `updated_at` on writes.
    # TODO(rel): You can add Relationship to DeckCard if you frequently load deck lines.


class DeckCard(SQLModel, table=True):
    """
    Link table between Decks and Cards.

    Attributes:
        deck_id: Foreign key to Deck.
        card_id: Foreign key to Card.
        quantity: Number of this card in the deck.
        role: Optional role label (starter, finisher, energy, etc.).

    Invariants:
        - Only one row per (deck_id, card_id). You enforce this at runtime in
          database.ensure_indexes(); consider a schema-level UNIQUE index too.
    """

    id: int = Field(default=None, primary_key=True)
    deck_id: int = Field(foreign_key="deck.id")
    card_id: str = Field(foreign_key="card.id")
    quantity: int = Field(default=1)
    role: Optional[str] = None

    # TODO(index): UNIQUE(deck_id, card_id) at schema/migration level for stronger guarantees.
