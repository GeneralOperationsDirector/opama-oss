"""
Showcase models — named collections of cards (like playlists).

Owned by the `showcase` plugin (premium tier). Moved out of
services/shared/models_showcase.py so the showcase plugin can be
disabled/removed without dragging premium tables into the core schema.

Design:
- Users can create multiple showcases with custom titles
- Each showcase can be public or private
- Cards can appear in multiple showcases
- Uniqueness constraint on (showcase_id, card_id) prevents duplicates
- Similar pattern to Deck/DeckCard but simplified (no role, add notes)
"""

from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field


class Showcase(SQLModel, table=True):
    """
    Represents a user's card showcase (collection/playlist).

    Attributes:
        id: Auto-increment primary key.
        user_id: Owner (foreign key to User table).
        title: Display name for the showcase (e.g., "Full Art Collection").
        description: Optional longer description.
        is_public: Whether this showcase appears on user's public profile.
        created_at: When the showcase was created (UTC).
        updated_at: Last modification time (UTC).
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    title: str
    description: Optional[str] = None
    is_public: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ShowcaseCard(SQLModel, table=True):
    """
    Link table between Showcases and Cards.

    Attributes:
        id: Auto-increment primary key.
        showcase_id: Foreign key to Showcase.
        card_id: Card ID (string) — soft reference, no DB-level FK (see below).
        quantity: How many of this card to display (default 1).
        notes: Optional per-card notes (e.g., "Looking to trade", "Mint PSA 10").
        added_at: When the card was added to this showcase (UTC).

    Constraints:
        (showcase_id, card_id) must be unique to prevent duplicates.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    showcase_id: int = Field(foreign_key="showcase.id", index=True)
    # Soft reference: `card` lives in the optional opama_pokemon_tcg external
    # plugin and may not exist in this deployment's schema (e.g. core-only installs).
    card_id: str = Field(index=True)
    quantity: int = Field(default=1, ge=1)
    notes: Optional[str] = None
    added_at: datetime = Field(default_factory=datetime.utcnow)
