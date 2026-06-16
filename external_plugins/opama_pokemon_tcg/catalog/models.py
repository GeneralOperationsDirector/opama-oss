"""
Catalog models — Pokémon TCG sets, cards, AI-suggestion features, and sync tracking.

Owned by the `catalog` plugin (premium tier). Moved out of services/shared/models.py
so the catalog plugin can be disabled/removed without dragging premium tables into
the core schema.
"""

from typing import Optional, List
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship, Column, JSON

# ---------------------------------------------------------------------------
# Catalog: Sets and Cards
# ---------------------------------------------------------------------------


class Set(SQLModel, table=True):
    """
    Represents a Pokémon TCG set (e.g., "Scarlet & Violet — 151").

    Attributes:
        id: Set code (e.g., "sv9").
        name: Human-readable name.
        series: Parent series name.
        release_date: Optional release date string (YYYY-MM-DD).
        printed_total: Number of cards actually printed.
        total: Total number of cards in the set.
        ptcgo_code: PTCGO identifier.
        cards: Relationship back to contained Card records.
    """

    # NOTE: Keep id stable; many external tools depend on it as a natural key.
    id: str = Field(primary_key=True)
    name: str
    series: str
    release_date: Optional[str] = None
    printed_total: Optional[int] = None
    total: Optional[int] = None
    ptcgo_code: Optional[str] = None

    # Relationship to Card; back_populates mirrors Card.set below
    cards: List["Card"] = Relationship(back_populates="set")


class Card(SQLModel, table=True):
    """
    Represents a Pokémon TCG card.

    Attributes include:
      - Identifiers (id, number, set_id)
      - Gameplay metadata (rarity, type, stage, hp, abilities, attacks)
      - Flavor data (illustrator, flavor_text)
      - Legality fields (standard, expanded, unlimited)
      - Media (small/large image URLs)
      - Sorting helpers (number_sort)
    """

    id: str = Field(primary_key=True)  # e.g., "sv10-49", stable primary key
    name: str
    number: Optional[str] = None
    rarity: Optional[str] = None
    supertype: Optional[str] = None
    subtypes: Optional[str] = None
    types: Optional[str] = None
    stage: Optional[str] = None
    hp: Optional[str] = None
    evolves_from: Optional[str] = None
    regulation_mark: Optional[str] = None

    # Abilities
    illustrator: Optional[str] = None
    ability_name: Optional[str] = None
    ability_text: Optional[str] = None
    ability_type: Optional[str] = None

    # Attacks (up to 3)
    attack1_name: Optional[str] = None
    attack1_cost: Optional[str] = None
    attack1_damage: Optional[str] = None
    attack1_text: Optional[str] = None

    attack2_name: Optional[str] = None
    attack2_cost: Optional[str] = None
    attack2_damage: Optional[str] = None
    attack2_text: Optional[str] = None

    attack3_name: Optional[str] = None
    attack3_cost: Optional[str] = None
    attack3_damage: Optional[str] = None
    attack3_text: Optional[str] = None

    # Other attributes
    weaknesses: Optional[str] = None
    resistances: Optional[str] = None
    retreat_cost: Optional[int] = None
    rules_text: Optional[str] = None
    flavor_text: Optional[str] = None

    # Legalities
    legal_standard: Optional[str] = None
    legal_expanded: Optional[str] = None
    legal_unlimited: Optional[str] = None

    national_pokedex_numbers: Optional[str] = None
    release_date: Optional[str] = None
    tcgplayer_product_id: Optional[str] = None

    # Media
    image_small: Optional[str] = None
    image_large: Optional[str] = None

    # Sorting helper
    number_sort: Optional[int] = None  # e.g., zero-padded number for stable sort

    # Relationships
    set_id: str = Field(foreign_key="set.id")
    set: Optional[Set] = Relationship(back_populates="cards")


# ---------------------------------------------------------------------------
# Card Features (for AI-based suggestions)
# ---------------------------------------------------------------------------


class CardFeatures(SQLModel, table=True):
    """
    Computed/curated features of a card used by suggestion algorithms.

    Attributes:
        energy_cost: Cost string.
        energy_types: Comma-separated energy types.
        provides_*: Boolean feature flags for AI recommendations.
        tags_json: Additional tags as JSON blob (free-form).

    Notes:
        - Primary key is card_id; this is an optional extension row for Card.
        - On SQLite, SQLAlchemy's JSON maps to TEXT under the hood (OK for us).
    """

    card_id: str = Field(primary_key=True, foreign_key="card.id")

    # Energy/typing
    energy_cost: Optional[str] = None
    energy_types: Optional[str] = None

    # Feature flags
    provides_draw: Optional[bool] = None
    provides_search: Optional[bool] = None
    switching: Optional[bool] = None
    gust_effect: Optional[bool] = None
    stadium: Optional[bool] = None
    healing: Optional[bool] = None
    disruption: Optional[bool] = None
    recovery: Optional[bool] = None

    # Serialized tags (stored as JSON)
    tags_json: Optional[str] = Field(default=None, sa_column=Column(JSON))


# ---------------------------------------------------------------------------
# Catalog Sync Tracking
# ---------------------------------------------------------------------------
#
# Tracks synchronization history between the Pokemon TCG API and the local
# database: when syncs occurred, what was synced, success/failure, and errors.


class CatalogSyncLog(SQLModel, table=True):
    """
    Tracks each catalog synchronization run.

    A sync log is created when a sync operation starts, and updated when it completes.
    This provides a historical record of all sync attempts.
    """

    __tablename__ = "catalogsynclog"

    id: Optional[int] = Field(default=None, primary_key=True)

    # Sync metadata
    sync_type: str = Field(
        default="scheduled",
        description="Type of sync: 'scheduled', 'manual', or 'initial'"
    )
    started_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the sync started"
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="When the sync completed (None if still running)"
    )

    # Sync status
    status: str = Field(
        default="running",
        description="Status: 'running', 'success', 'partial', 'failed'"
    )

    # Statistics
    sets_discovered: int = Field(
        default=0,
        description="Number of new sets discovered in API"
    )
    sets_synced: int = Field(
        default=0,
        description="Number of sets successfully synced"
    )
    sets_failed: int = Field(
        default=0,
        description="Number of sets that failed to sync"
    )

    # Error tracking
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if sync failed"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "id": 1,
                "sync_type": "scheduled",
                "started_at": "2025-11-26T02:00:00Z",
                "completed_at": "2025-11-26T02:05:30Z",
                "status": "success",
                "sets_discovered": 2,
                "sets_synced": 2,
                "sets_failed": 0,
                "error_message": None
            }
        }


class SetSyncStatus(SQLModel, table=True):
    """
    Tracks synchronization status for individual sets.

    Each set gets one row that's updated whenever the set is synced.
    This allows us to track:
    - When a set was last synced
    - How many cards it has
    - If the last sync succeeded or failed
    """

    __tablename__ = "setsyncstatus"

    # Primary key is the set_id (matches Set.id)
    set_id: str = Field(
        primary_key=True,
        description="Pokemon TCG API set ID (e.g., 'me1', 'sv10')"
    )

    # Sync tracking
    last_synced_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When this set was last synced"
    )
    cards_count: int = Field(
        default=0,
        description="Number of cards imported for this set"
    )

    # Status tracking
    sync_status: str = Field(
        default="success",
        description="Status: 'success', 'failed', 'pending'"
    )
    error_details: Optional[str] = Field(
        default=None,
        description="Error details if sync failed"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "set_id": "me1",
                "last_synced_at": "2025-11-26T02:03:15Z",
                "cards_count": 132,
                "sync_status": "success",
                "error_details": None
            }
        }
