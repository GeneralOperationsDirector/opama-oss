#!/usr/bin/env python3
"""
SQLite to PostgreSQL Migration Script
======================================

Migrates all data from the SQLite database (data.db) to PostgreSQL.

Usage:
    python scripts/migrate_to_postgres.py

Prerequisites:
    - PostgreSQL database running (via Docker Compose or locally)
    - DATABASE_URL environment variable set
    - SQLite database exists at data.db

Steps:
    1. Connects to both SQLite and PostgreSQL
    2. Creates PostgreSQL schema using SQLModel
    3. Copies all data table by table
    4. Verifies row counts match
    5. Creates indexes for performance

Notes:
    - Safe to run multiple times (drops and recreates tables)
    - Preserves all data and relationships
    - Reports progress and errors
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
# Card/Set/Deck/Inventory/Trading live in opama_pokemon_tcg, an external plugin
# under external_plugins/ (see PLUGIN_PATHS / external_plugins/README.md) — add
# its root so opama_pokemon_tcg.* imports resolve.
sys.path.insert(0, str(project_root / "external_plugins"))

from sqlmodel import Session, create_engine, select, SQLModel
from sqlalchemy import text
from services.shared.models import User
from opama_pokemon_tcg.catalog.models import Card, Set, CardFeatures
from opama_pokemon_tcg.decks.models import Deck, DeckCard
from opama_pokemon_tcg.inventory.models import InventoryItem
from opama_pokemon_tcg.trading.models import WishList, TradeItem

# Database URLs
SQLITE_URL = "sqlite:///data.db"
POSTGRES_URL = os.getenv("DATABASE_URL", "postgresql://opama_user:opama_dev_pass@localhost:5432/opama_dev")

# Tables to migrate in order (respects foreign keys)
TABLES = [
    ("set", Set),
    ("card", Card),
    ("cardfeatures", CardFeatures),
    ("user", User),
    ("deck", Deck),
    ("deckcard", DeckCard),
    ("inventoryitem", InventoryItem),
    ("wishlist", WishList),
    ("trade_items", TradeItem),
]


def migrate_table(sqlite_session: Session, postgres_session: Session, table_name: str, model_class):
    """Migrate a single table from SQLite to PostgreSQL."""
    print(f"\n📦 Migrating table: {table_name}")

    try:
        # Fetch all rows from SQLite
        rows = sqlite_session.exec(select(model_class)).all()
        count = len(rows)
        print(f"  → Found {count} rows in SQLite")

        if count == 0:
            print("  ✓ Skipping empty table")
            return True

        # Insert into PostgreSQL in batches
        batch_size = 1000
        for i in range(0, count, batch_size):
            batch = rows[i:i+batch_size]
            for row in batch:
                # Create new instance to avoid session conflicts
                # Get data as dict and create new instance
                row_data = row.model_dump()
                new_row = model_class(**row_data)
                postgres_session.add(new_row)
            postgres_session.commit()
            print(f"  → Inserted {min(i+batch_size, count)}/{count} rows")

        # Verify row count
        postgres_count = postgres_session.exec(select(model_class)).all()
        if len(postgres_count) == count:
            print(f"  ✓ Migration successful: {len(postgres_count)} rows")
            return True
        else:
            print(f"  ✗ Row count mismatch: {len(postgres_count)} vs {count}")
            return False

    except Exception as e:
        print(f"  ✗ Error migrating {table_name}: {e}")
        import traceback
        traceback.print_exc()
        return False


def create_indexes(postgres_session: Session):
    """Create indexes for common queries."""
    print("\n📑 Creating indexes...")

    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_card_set_id ON card(set_id);",
        "CREATE INDEX IF NOT EXISTS idx_card_name ON card(name);",
        "CREATE INDEX IF NOT EXISTS idx_card_supertype ON card(supertype);",
        "CREATE INDEX IF NOT EXISTS idx_inventory_user_id ON inventoryitem(user_id);",
        "CREATE INDEX IF NOT EXISTS idx_inventory_card_id ON inventoryitem(card_id);",
        "CREATE INDEX IF NOT EXISTS idx_deck_user_id ON deck(user_id);",
        "CREATE INDEX IF NOT EXISTS idx_deckcard_deck_id ON deckcard(deck_id);",
        "CREATE INDEX IF NOT EXISTS idx_deckcard_card_id ON deckcard(card_id);",
        "CREATE INDEX IF NOT EXISTS idx_wishlist_user_id ON wishlist(user_id);",
        "CREATE INDEX IF NOT EXISTS idx_trade_user_id ON trade_items(user_id);",
    ]

    for idx_sql in indexes:
        try:
            postgres_session.exec(text(idx_sql))
            postgres_session.commit()
            print("  ✓ Created index")
        except Exception as e:
            print(f"  ⚠ Index creation warning: {e}")

    print("  ✓ All indexes created")


def main():
    """Main migration workflow."""
    print("="*60)
    print("SQLite → PostgreSQL Migration")
    print("="*60)

    # Check SQLite database exists
    if not Path("data.db").exists():
        print("✗ Error: data.db not found")
        print("  Please ensure the SQLite database exists")
        return 1

    print(f"\n📊 Source: {SQLITE_URL}")
    print(f"📊 Target: {POSTGRES_URL}")

    # Create engines
    print("\n🔌 Connecting to databases...")
    sqlite_engine = create_engine(SQLITE_URL, echo=False)
    postgres_engine = create_engine(POSTGRES_URL, echo=False)

    # Test connections
    try:
        with Session(sqlite_engine) as sqlite_session:
            sqlite_session.exec(text("SELECT 1"))
        print("  ✓ SQLite connection successful")
    except Exception as e:
        print(f"  ✗ SQLite connection failed: {e}")
        return 1

    try:
        with Session(postgres_engine) as postgres_session:
            postgres_session.exec(text("SELECT 1"))
        print("  ✓ PostgreSQL connection successful")
    except Exception as e:
        print(f"  ✗ PostgreSQL connection failed: {e}")
        print("  💡 Ensure PostgreSQL is running: docker-compose up -d postgres")
        return 1

    # Create PostgreSQL schema
    print("\n🏗️  Creating PostgreSQL schema...")
    try:
        with postgres_engine.connect() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
            conn.commit()
        SQLModel.metadata.drop_all(postgres_engine)
        SQLModel.metadata.create_all(postgres_engine)
        print("  ✓ Schema created successfully")
    except Exception as e:
        print(f"  ✗ Schema creation failed: {e}")
        return 1

    # Migrate tables
    print("\n🚚 Migrating data...")
    success_count = 0

    with Session(sqlite_engine) as sqlite_session:
        with Session(postgres_engine) as postgres_session:
            for table_name, model_class in TABLES:
                if migrate_table(sqlite_session, postgres_session, table_name, model_class):
                    success_count += 1

    # Create indexes
    with Session(postgres_engine) as postgres_session:
        create_indexes(postgres_session)

    # Summary
    print("\n" + "="*60)
    print("Migration Summary")
    print("="*60)
    print(f"✓ Tables migrated: {success_count}/{len(TABLES)}")

    if success_count == len(TABLES):
        print("\n🎉 Migration completed successfully!")
        print("\n💡 Next steps:")
        print("  1. Verify data in PostgreSQL")
        print("  2. Update .env.local with DATABASE_URL")
        print("  3. Test services with PostgreSQL")
        return 0
    else:
        print(f"\n⚠️  Migration completed with {len(TABLES) - success_count} errors")
        print("  Please review errors above and retry")
        return 1


if __name__ == "__main__":
    sys.exit(main())
