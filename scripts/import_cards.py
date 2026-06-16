#!/usr/bin/env python3
# scripts/import_cards.py
"""
Bulk-import Set and Card rows from a directory of CSV files.

Directory layout (flexible)
  <root>/
    <series_name>/                 # optional — becomes Set.series
      sv9_Journey Together.csv     # "sv9_<Human Readable Name>.csv"
      sv10_Destined Rivals.csv
    standalone.csv                 # also accepted (series becomes parent dir name)

Filename -> Set mapping
- If the base filename contains "_", split once:
    "<set_id>_<set_name>.csv"  →  Set(id=<set_id>, name=<set_name>)
- Otherwise, base name used for both id and name.

Behavior
- Creates Set rows on demand (idempotent).
- For each CSV row:
  - Finds Card by `id` (or `card_id`), else creates a new Card stub.
  - Updates any attributes present in CSV if the Card has that attribute.
  - Commits once per file for safety/speed.
- Prints per-file counts (added/updated) and a final summary.

CLI
  python scripts/import_cards.py <data_dir>

Notes
- Defaults are conservative: no deletes, no truncation.
- CSVs are read with utf-8-sig to tolerate BOM.
"""

from __future__ import annotations

import sys
import os
import csv
import pathlib
from typing import Dict, Any, Tuple

# --- Ensure repo root is on sys.path BEFORE importing app.* ------------------
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# Card/Set live in opama_pokemon_tcg, an external plugin under external_plugins/
# (see PLUGIN_PATHS / external_plugins/README.md) — add its root so
# opama_pokemon_tcg.* imports resolve.
EXTERNAL_PLUGINS = ROOT / "external_plugins"
if str(EXTERNAL_PLUGINS) not in sys.path:
    sys.path.insert(0, str(EXTERNAL_PLUGINS))

from sqlmodel import Session, create_engine  # type: ignore
from opama_pokemon_tcg.catalog.models import Set, Card  # type: ignore
from services.shared.database import DB_URL  # type: ignore


# ------------------------------- utils --------------------------------------


def _parse_set_from_path(path: str) -> Tuple[str, str, str]:
    """
    Return (set_id, set_name, series) for a given CSV file path.
    - series is the parent directory name (or "" at repo root).
    - set_id and set_name come from the file's base name.
    """
    base = os.path.basename(path)[:-4]  # strip .csv
    if "_" in base:
        set_id, set_name = base.split("_", 1)
    else:
        set_id, set_name = base, base
    series = os.path.basename(os.path.dirname(path)) or ""
    return set_id, set_name.replace("_", " ").strip(), series


def _safe_int(v: Any) -> Any:
    """Cast to int when it looks like one; otherwise return original."""
    if v is None:
        return v
    s = str(v).strip()
    if s == "":
        return None
    try:
        return int(s)
    except Exception:
        return v


def _assign_attrs(obj: Any, row: Dict[str, Any]) -> None:
    """
    Assign row fields onto `obj` if the attribute exists and the value is non-empty.
    Also tries to set a few common numeric fields as ints.
    """
    for k, v in row.items():
        if v in (None, ""):
            continue
        if hasattr(obj, k):
            if k in {"hp", "retreat_cost", "number_sort"}:
                v = _safe_int(v)
            setattr(obj, k, v)

    # If the model has number_sort and we have a number like "123a", fill number_sort with 123.
    if hasattr(obj, "number_sort") and getattr(obj, "number_sort", None) in (
        None,
        "",
        0,
    ):
        num = str(getattr(obj, "number", "") or "").strip()
        digits = "".join(ch for ch in num if ch.isdigit())
        if digits:
            try:
                setattr(obj, "number_sort", int(digits))
            except Exception:
                pass


# ------------------------------- core ---------------------------------------


def import_dir(root: str) -> None:
    """
    Walk `root` recursively; import every *.csv into Sets/Cards.
    """
    engine = create_engine(DB_URL, echo=False)
    total_files = 0
    total_added = 0
    total_updated = 0

    with Session(engine) as session:
        for dirpath, _, filenames in os.walk(root):
            for fn in filenames:
                if not fn.lower().endswith(".csv"):
                    continue

                path = os.path.join(dirpath, fn)
                set_id, set_name, series = _parse_set_from_path(path)

                # Upsert Set
                s = session.get(Set, set_id)
                if not s:
                    s = Set(id=set_id, name=set_name, series=series)
                    session.add(s)
                    session.commit()
                else:
                    # Keep Set name/series up-to-date if CSV changes naming.
                    dirty = False
                    if set_name and getattr(s, "name", None) != set_name:
                        s.name = set_name
                        dirty = True
                    if series and getattr(s, "series", None) != series:
                        s.series = series
                        dirty = True
                    if dirty:
                        session.add(s)
                        session.commit()

                added = 0
                updated = 0

                # Import Cards for this file
                with open(path, "r", encoding="utf-8-sig", newline="") as f:
                    reader = csv.DictReader(f)
                    for r in reader:
                        # Prefer 'id', fall back to 'card_id'
                        cid = (r.get("id") or r.get("card_id") or "").strip()
                        if not cid:
                            # Last resort: compose from set_id + number if present
                            num = (r.get("number") or "").strip()
                            if num:
                                cid = f"{set_id}-{num}"
                            else:
                                continue  # skip unidentifiable rows

                        c = session.get(Card, cid)
                        if not c:
                            c = Card(
                                id=cid, set_id=set_id, name=r.get("name", "") or ""
                            )
                            _assign_attrs(c, r)
                            session.add(c)
                            added += 1
                        else:
                            # Update in place
                            _assign_attrs(c, r)
                            updated += 1

                    session.commit()

                total_files += 1
                total_added += added
                total_updated += updated
                print(f"Imported {path}  (+{added}, ~{updated})")

    print(
        f"\nDone. Files: {total_files}, Cards added: {total_added}, updated: {total_updated}"
    )


# ------------------------------- CLI ----------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/import_cards.py <data_dir>")
        sys.exit(1)

    data_dir = sys.argv[1]
    if not os.path.isdir(data_dir):
        print(f"Error: {data_dir!r} is not a directory")
        sys.exit(2)

    import_dir(data_dir)
