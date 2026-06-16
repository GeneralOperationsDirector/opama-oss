"""
Baseline catalog seed — loads the bundled Set + Card snapshot
(`data/baseline_catalog.ndjson.gz`) into a fresh database.

Counterpart to `scripts/export_baseline_catalog.py` (which generates the
bundled file from a maintainer's instance). Called once from
`app/main.py`'s startup handler, after `init_db()`, only when the `catalog`
plugin is loaded. Idempotent by construction: it bails out as soon as the
`Set` table already has any rows, so re-running on an already-seeded or
user-synced instance is a no-op.

This is a one-time fast-start for self-hosted installs — the ongoing path
for new sets as Pokémon TCG releases them is `POST /cards/sync/trigger`,
which pulls directly from the live Pokémon TCG API and only adds sets not
already present (so it composes cleanly with this seed).
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

from sqlmodel import Session, select

from opama_pokemon_tcg.catalog.models import Card, Set

DATA_FILE = Path(__file__).resolve().parent / "data" / "baseline_catalog.ndjson.gz"


def seed_baseline_catalog(session: Session) -> tuple[int, int] | None:
    """Load the bundled baseline catalog if the Set table is empty.

    Returns (sets_added, cards_added), or None if seeding was skipped
    (catalog already populated, or no bundled dataset present).
    """
    if session.exec(select(Set.id).limit(1)).first() is not None:
        return None
    if not DATA_FILE.exists():
        return None

    set_rows: list[dict] = []
    card_rows: list[dict] = []
    with gzip.open(DATA_FILE, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            row_type = row.pop("_type", None)
            if row_type == "set":
                set_rows.append(row)
            elif row_type == "card":
                card_rows.append(row)

    if set_rows:
        session.bulk_insert_mappings(Set, set_rows)
    if card_rows:
        session.bulk_insert_mappings(Card, card_rows)
    session.commit()

    return len(set_rows), len(card_rows)
