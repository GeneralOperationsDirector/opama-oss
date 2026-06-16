#!/usr/bin/env python3
"""
Database Migration: Add Price Tracking and Grading Fields to InventoryItem

This migration adds the following fields to the inventoryitem table:
- grade (INTEGER) - Professional grading score 1-10
- grading_company (VARCHAR) - Grading service (PSA, BGS, CGC)
- sale_price_per_card (FLOAT) - Sale price per card
- sale_date (TIMESTAMP) - When sold
- sale_platform (VARCHAR) - Where sold

It also renames:
- purchase_price -> purchase_price_per_card (for clarity)

Usage:
    python scripts/migrate_inventory_price_tracking.py
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load environment variables
load_dotenv('.env.local')
load_dotenv('.env')

DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not found in environment")
    sys.exit(1)

print("Connecting to database...")
engine = create_engine(DATABASE_URL)


def run_migration():
    """Apply the migration to add price tracking fields."""

    migrations = [
        # Add grading fields
        """
        ALTER TABLE inventoryitem
        ADD COLUMN IF NOT EXISTS grade INTEGER;
        """,
        """
        ALTER TABLE inventoryitem
        ADD COLUMN IF NOT EXISTS grading_company VARCHAR(50);
        """,

        # Add sale tracking fields
        """
        ALTER TABLE inventoryitem
        ADD COLUMN IF NOT EXISTS sale_price_per_card FLOAT;
        """,
        """
        ALTER TABLE inventoryitem
        ADD COLUMN IF NOT EXISTS sale_date TIMESTAMP;
        """,
        """
        ALTER TABLE inventoryitem
        ADD COLUMN IF NOT EXISTS sale_platform VARCHAR(200);
        """,

        # Rename purchase_price to purchase_price_per_card for clarity
        # Note: This uses a safe approach - copy data, drop old, rename new
        """
        DO $$
        BEGIN
            -- Check if old column exists and new one doesn't
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'inventoryitem'
                AND column_name = 'purchase_price'
            ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'inventoryitem'
                AND column_name = 'purchase_price_per_card'
            ) THEN
                -- Add new column
                ALTER TABLE inventoryitem ADD COLUMN purchase_price_per_card FLOAT;

                -- Copy data from old to new
                UPDATE inventoryitem SET purchase_price_per_card = purchase_price;

                -- Drop old column
                ALTER TABLE inventoryitem DROP COLUMN purchase_price;
            END IF;
        END $$;
        """,
    ]

    with engine.begin() as conn:
        print("\n" + "="*60)
        print("Running Price Tracking Migration")
        print("="*60)

        for i, migration_sql in enumerate(migrations, 1):
            try:
                print(f"\n[{i}/{len(migrations)}] Executing migration...")
                conn.execute(text(migration_sql))
                print(f"✓ Migration {i} completed successfully")
            except Exception as e:
                print(f"✗ Migration {i} failed: {e}")
                raise

        print("\n" + "="*60)
        print("Migration completed successfully!")
        print("="*60)

        # Verify the new columns exist
        print("\nVerifying new schema...")
        result = conn.execute(text("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'inventoryitem'
            AND column_name IN (
                'grade', 'grading_company',
                'purchase_price_per_card',
                'sale_price_per_card', 'sale_date', 'sale_platform'
            )
            ORDER BY column_name;
        """))

        print("\nNew columns:")
        for row in result:
            print(f"  - {row[0]}: {row[1]}")

        print("\n✓ Schema verification complete")


def verify_migration():
    """Verify that the migration was successful."""
    with engine.begin() as conn:
        # Check table structure
        result = conn.execute(text("""
            SELECT COUNT(*) as count
            FROM information_schema.columns
            WHERE table_name = 'inventoryitem'
            AND column_name IN (
                'grade', 'grading_company',
                'purchase_price_per_card',
                'sale_price_per_card', 'sale_date', 'sale_platform'
            );
        """))

        count = result.scalar()
        expected_columns = 6

        if count == expected_columns:
            print(f"\n✓ All {expected_columns} new columns exist")
            return True
        else:
            print(f"\n✗ Expected {expected_columns} columns, found {count}")
            return False


if __name__ == "__main__":
    print("="*60)
    print("InventoryItem Price Tracking Migration")
    print("="*60)
    print("\nThis will add the following fields:")
    print("  - grade (professional grading score)")
    print("  - grading_company (PSA, BGS, CGC, etc.)")
    print("  - purchase_price_per_card (renamed from purchase_price)")
    print("  - sale_price_per_card (when sold)")
    print("  - sale_date (when sold)")
    print("  - sale_platform (where sold)")
    print("\n" + "="*60)

    response = input("\nProceed with migration? (yes/no): ").strip().lower()

    if response != 'yes':
        print("Migration cancelled")
        sys.exit(0)

    try:
        run_migration()

        if verify_migration():
            print("\n" + "="*60)
            print("✓ Migration completed and verified successfully!")
            print("="*60)
        else:
            print("\n" + "="*60)
            print("⚠ Migration completed but verification failed")
            print("="*60)
            sys.exit(1)

    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        sys.exit(1)
