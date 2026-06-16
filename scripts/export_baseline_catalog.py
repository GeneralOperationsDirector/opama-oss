#!/usr/bin/env python3
# scripts/export_baseline_catalog.py
"""
Export the Set + Card catalog to the bundled baseline dataset shipped with
the Pokémon TCG module:

    external_plugins/opama_pokemon_tcg/catalog/data/baseline_catalog.ndjson.gz

This is the "refresh" half of the baseline-catalog pair (the other half is
`opama_pokemon_tcg.catalog.seed.seed_baseline_catalog`, which loads this file
into a fresh database on first startup). Re-run this script periodically as
new Pokémon TCG sets are released and synced into a maintainer's instance
(via `POST /cards/sync/trigger`), so future installs ship with an up-to-date
baseline. Tie this to release points alongside `scripts/sync_oss_module.sh`
(see docs/RELEASE_PROCESS.md) — not a per-commit step.

Output is one JSON object per line, each tagged with `_type` ("set" or
"card") so `seed.py` can dispatch without a second file. Columns are read
directly off the SQLModel tables (`__table__.columns`), so the export always
matches the current schema — no hardcoded field list to keep in sync.

Contains only catalog metadata (names, numbers, sets/series, rarity,
abilities/attacks text, legality, etc.) — no card artwork is bundled.
`image_small` / `image_large` are plain URL strings pointing at the official
Pokémon TCG API's image CDN when populated (or null), never local files.

CLI
  python scripts/export_baseline_catalog.py [output_path]
"""

from __future__ import annotations

import gzip
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# Set/Card live in opama_pokemon_tcg, an external plugin under
# external_plugins/ (see PLUGIN_PATHS / external_plugins/README.md).
EXTERNAL_PLUGINS = ROOT / "external_plugins"
if str(EXTERNAL_PLUGINS) not in sys.path:
    sys.path.insert(0, str(EXTERNAL_PLUGINS))

from sqlmodel import Session, create_engine, select  # type: ignore

from opama_pokemon_tcg.catalog.models import Card, Set  # type: ignore
from services.shared.database import DB_URL  # type: ignore

DEFAULT_OUTPUT = (
    EXTERNAL_PLUGINS / "opama_pokemon_tcg" / "catalog" / "data" / "baseline_catalog.ndjson.gz"
)

SET_COLUMNS = [c.name for c in Set.__table__.columns]
CARD_COLUMNS = [c.name for c in Card.__table__.columns]


def export(output_path: pathlib.Path) -> None:
    engine = create_engine(DB_URL)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with Session(engine) as session, gzip.open(output_path, "wt", encoding="utf-8") as f:
        sets = session.exec(select(Set).order_by(Set.id)).all()
        for s in sets:
            row = {col: getattr(s, col) for col in SET_COLUMNS}
            row["_type"] = "set"
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

        cards = session.exec(select(Card).order_by(Card.id)).all()
        for c in cards:
            row = {col: getattr(c, col) for col in CARD_COLUMNS}
            row["_type"] = "card"
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Exported {len(sets)} sets, {len(cards)} cards -> {output_path}")


if __name__ == "__main__":
    out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    export(out)
