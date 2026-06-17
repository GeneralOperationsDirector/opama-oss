"""
Database setup — supports both SQLite (dev) and PostgreSQL (production).

DATABASE_URL env var controls which backend is used:
  - Not set: SQLite at data.db
  - Set to postgresql://...: PostgreSQL

Alembic manages schema migrations. ensure_indexes() creates performance
indexes that Alembic doesn't manage (they're not tied to model definitions).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

from sqlalchemy import inspect as sa_inspect, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, Session, create_engine

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "data.db"

DATABASE_URL = os.getenv("DATABASE_URL", "")

if DATABASE_URL:
    # Normalize postgres:// → postgresql:// (Heroku/Render use the old scheme)
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    DB_URL = DATABASE_URL
    connect_args: dict = {}
else:
    DB_URL = f"sqlite:///{DB_PATH}"
    connect_args = {"check_same_thread": False}

engine = create_engine(DB_URL, connect_args=connect_args)

_is_sqlite = DB_URL.startswith("sqlite")

# Register the RLS active-org GUC listener (pool tenancy). Import for its side
# effect: the `after_begin` hook that re-applies `app.current_org_id` per
# transaction. No-op on non-Postgres binds / unstamped sessions.
from services.shared import rls  # noqa: E402,F401


# ---------------------------------------------------------------------------
# SQLite PRAGMAs
# ---------------------------------------------------------------------------

if _is_sqlite:
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
            conn.exec_driver_sql("PRAGMA synchronous=NORMAL;")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Schema init / session helpers
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create all tables (idempotent). Called on startup; Alembic handles diffs."""
    SQLModel.metadata.create_all(engine)
    ensure_indexes()


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session


get_db = get_session  # back-compat alias


# ---------------------------------------------------------------------------
# get_backend (legacy compatibility)
# ---------------------------------------------------------------------------

def get_backend() -> str:
    import json
    cfg_path = Path("/app/config.json")
    if cfg_path.exists():
        try:
            return json.loads(cfg_path.read_text()).get("db_backend", "sqlite")
        except Exception:
            pass
    return "sqlite"


# ---------------------------------------------------------------------------
# Indexes — database-agnostic helpers
# ---------------------------------------------------------------------------

def _table_exists(session: Session, table: str) -> bool:
    inspector = sa_inspect(engine)
    return table in inspector.get_table_names()


def _index_sql(unique: bool, name: str, table: str, cols: str) -> str:
    u = "UNIQUE " if unique else ""
    return f"CREATE {u}INDEX IF NOT EXISTS {name} ON {table}({cols})"


def ensure_indexes() -> None:
    """
    Ensure performance + integrity indexes exist. Safe to call repeatedly.
    Works with both SQLite and PostgreSQL.
    """
    with Session(engine) as s:
        try:
            # ── InventoryItem ──────────────────────────────────────────────
            s.exec(text(_index_sql(False, "ix_inventory_user", "inventoryitem", "user_id")))
            s.exec(text(_index_sql(False, "ix_inventory_card", "inventoryitem", "card_id")))
            s.exec(text(_index_sql(False, "ix_inventory_user_card", "inventoryitem", "user_id, card_id")))
            s.exec(text(_index_sql(False, "ix_inventory_identity", "inventoryitem",
                "user_id, card_id, condition, is_holo, is_reverse_holo, is_alt_art")))

            # ── Deck / DeckCard ────────────────────────────────────────────
            s.exec(text(_index_sql(False, "ix_deck_user",      "deck",     "user_id")))
            s.exec(text(_index_sql(False, "ix_deckcard_deck",  "deckcard", "deck_id")))
            s.exec(text(_index_sql(False, "ix_deckcard_card",  "deckcard", "card_id")))
            s.exec(text(_index_sql(False, "ix_deckcard_deck_card", "deckcard", "deck_id, card_id")))
            s.commit()

        except Exception as e:
            s.rollback()
            print(f"⚠️  Index creation error (non-unique): {e}")

        # Unique index on DeckCard — dedupe first if needed
        try:
            s.exec(text(_index_sql(True, "ux_deckcard_deck_card", "deckcard", "deck_id, card_id")))
            s.commit()
        except IntegrityError:
            s.rollback()
            _dedupe_deckcards(s)
            s.commit()
            s.exec(text(_index_sql(True, "ux_deckcard_deck_card", "deckcard", "deck_id, card_id")))
            s.commit()
        except Exception as e:
            s.rollback()
            print(f"⚠️  Unique index error: {e}")

        # ── Card ──────────────────────────────────────────────────────────
        try:
            s.exec(text(_index_sql(False, "ix_card_name",       "card", "name")))
            s.exec(text(_index_sql(False, "ix_card_set",        "card", "set_id")))
            s.exec(text(_index_sql(False, "ix_card_supertype",  "card", "supertype")))
            s.exec(text(_index_sql(False, "ix_card_set_number", "card", "set_id, number")))
            s.commit()
        except Exception as e:
            s.rollback()
            print(f"⚠️  Card index error: {e}")

        # ── Optional tables (created after initial migration) ──────────────
        for table, indexes in {
            "wishlist": [
                ("ix_wishlist_user", "user_id"),
                ("ix_wishlist_card", "card_id"),
            ],
            "tradeitem": [
                ("ix_tradeitem_user", "user_id"),
                ("ix_tradeitem_card", "card_id"),
            ],
            "showcase": [
                ("ix_showcase_user",   "user_id"),
                ("ix_showcase_public", "is_public"),
            ],
            "showcasecard": [
                ("ix_showcasecard_showcase", "showcase_id"),
                ("ix_showcasecard_card",     "card_id"),
            ],
        }.items():
            if not _table_exists(s, table):
                continue
            try:
                for idx_name, cols in indexes:
                    s.exec(text(_index_sql(False, idx_name, table, cols)))
                s.commit()
            except Exception as e:
                s.rollback()
                print(f"⚠️  Index error on {table}: {e}")

        # Unique on showcasecard
        if _table_exists(s, "showcasecard"):
            try:
                s.exec(text(_index_sql(True, "ux_showcasecard_showcase_card",
                    "showcasecard", "showcase_id, card_id")))
                s.commit()
            except Exception as e:
                s.rollback()
                print(f"⚠️  Showcase unique index: {e}")


# ---------------------------------------------------------------------------
# DeckCard deduplication
# ---------------------------------------------------------------------------

def _dedupe_deckcards(session: Session) -> None:
    rows = session.exec(text("SELECT id, deck_id, card_id, quantity FROM deckcard")).all()
    by_key: dict[tuple, list] = {}
    for id_, deck_id, card_id, qty in rows:
        by_key.setdefault((deck_id, card_id), []).append({"id": id_, "qty": qty})

    for group in by_key.values():
        if len(group) == 1:
            continue
        group.sort(key=lambda r: r["id"])
        total = sum(int(r["qty"] or 0) for r in group)
        session.exec(text("UPDATE deckcard SET quantity = :q WHERE id = :id").bindparams(
            q=total, id=group[0]["id"]))
        for r in group[1:]:
            session.exec(text("DELETE FROM deckcard WHERE id = :id").bindparams(id=r["id"]))
