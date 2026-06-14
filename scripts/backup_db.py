#!/usr/bin/env python3
# scripts/backup_db.py
"""
SQLite backup utility for `data.db`.

Default behavior (no flags):
- Backs up `<repo>/data.db` into `<repo>/backups/` using the SQLite *online backup* API
  (safe even while the app is running with WAL).
- Names the file `data_<YYYYMMDD>_<HHMMSS>.db`.
- Prints the backup path and exits 0.

Extras (optional):
- --verify        : run PRAGMA integrity_check on the *backup* before exiting
- --retain N      : keep only the latest N backups (delete older ones)
- --retain-days D : delete backups older than D days (applied after --retain)
- --compress {gz,zip} : compress the backup (removes the .db after compress)
- --db PATH       : override source database path (defaults to <repo>/data.db)
- --out-dir PATH  : override destination directory (defaults to <repo>/backups)

All options are best-effort; failures are surfaced with clear messages.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import shutil
import sys
import zipfile
import gzip

# ---------- Defaults (match original behavior) ----------
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data.db"
DEFAULT_OUT_DIR = ROOT / "backups"
TS_FMT = "%Y%m%d_%H%M%S"
FILENAME_PREFIX = "data_"
FILENAME_SUFFIX = ".db"


def _ensure_paths(db_path: Path, out_dir: Path) -> None:
    if not db_path.exists():
        raise SystemExit(f"No database found at: {db_path}")
    out_dir.mkdir(parents=True, exist_ok=True)


def _backup_sqlite(src: Path, dst: Path) -> None:
    """Use SQLite online backup API (safe with WAL)."""
    # sqlite3.connect accepts PathLike
    with sqlite3.connect(src) as conn_src, sqlite3.connect(dst) as conn_dst:
        conn_src.backup(conn_dst)  # copy entire DB


def _verify_sqlite(db_path: Path) -> tuple[bool, str]:
    """Return (ok, message) from PRAGMA integrity_check on db_path."""
    try:
        with sqlite3.connect(db_path) as conn:
            cur = conn.execute("PRAGMA integrity_check")
            row = cur.fetchone()
            msg = row[0] if row else "no result"
            return (msg == "ok", msg)
    except Exception as e:
        return (False, f"verify failed: {e}")


def _compress_gz(src_db: Path) -> Path:
    out = src_db.with_suffix(src_db.suffix + ".gz")
    with open(src_db, "rb") as f_in, gzip.open(out, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    src_db.unlink(missing_ok=True)
    return out


def _compress_zip(src_db: Path) -> Path:
    out = src_db.with_suffix(".zip")
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(src_db, arcname=src_db.name)
    src_db.unlink(missing_ok=True)
    return out


def _list_backups(out_dir: Path) -> list[Path]:
    return sorted(
        [
            p
            for p in out_dir.glob(f"{FILENAME_PREFIX}*{FILENAME_SUFFIX}")
            if p.is_file()
        ],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def _prune_backups(
    out_dir: Path, keep: int | None, keep_days: int | None
) -> list[Path]:
    deleted: list[Path] = []
    backups = _list_backups(out_dir)

    # Retain by count
    if keep is not None and keep >= 0 and len(backups) > keep:
        for p in backups[keep:]:
            try:
                p.unlink()
                deleted.append(p)
            except Exception:
                pass  # best-effort
        backups = backups[: keep or 0]

    # Retain by age
    if keep_days is not None and keep_days >= 0:
        threshold = datetime.now() - timedelta(days=keep_days)
        for p in list(backups):
            try:
                mtime = datetime.fromtimestamp(p.stat().st_mtime)
                if mtime < threshold:
                    p.unlink()
                    deleted.append(p)
                    backups.remove(p)
            except Exception:
                pass

    return deleted


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Backup SQLite database (safe with WAL).")
    ap.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help="Path to source database (default: <repo>/data.db)",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Directory to write backups (default: <repo>/backups)",
    )
    ap.add_argument(
        "--verify", action="store_true", help="Run PRAGMA integrity_check on the backup"
    )
    ap.add_argument(
        "--retain",
        type=int,
        default=None,
        help="Keep only the latest N backups (delete older)",
    )
    ap.add_argument(
        "--retain-days", type=int, default=None, help="Delete backups older than D days"
    )
    ap.add_argument(
        "--compress",
        choices=["gz", "zip"],
        default=None,
        help="Compress the backup and remove the .db",
    )
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ns = parse_args(argv or sys.argv[1:])

    _ensure_paths(ns.db, ns.out_dir)

    ts = datetime.now().strftime(TS_FMT)
    dst = ns.out_dir / f"{FILENAME_PREFIX}{ts}{FILENAME_SUFFIX}"

    # 1) Make the backup
    _backup_sqlite(ns.db, dst)
    print(f"Backup written to: {dst}")

    # 2) Optional verify
    if ns.verify:
        ok, msg = _verify_sqlite(dst)
        print(f"Verify: {msg}")
        if not ok:
            return 2

    # 3) Optional compression
    if ns.compress == "gz":
        dst = _compress_gz(dst)
        print(f"Compressed to: {dst}")
    elif ns.compress == "zip":
        dst = _compress_zip(dst)
        print(f"Compressed to: {dst}")

    # 4) Optional pruning
    deleted = _prune_backups(ns.out_dir, ns.retain, ns.retain_days)
    if deleted:
        print(f"Pruned {len(deleted)} old backup(s).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
