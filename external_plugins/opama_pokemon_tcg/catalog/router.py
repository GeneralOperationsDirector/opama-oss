# services/catalog/router.py
"""
Catalog Service - Cards & Sets API
-----------------------------------
Provides public endpoints to:
- Browse Pokémon TCG sets
- Search and fetch cards
- Export catalog data in JSON or NDJSON

This is a read-only service, candidate for CDN/caching in SOA.

Key features:
- Fast substring search with pagination
- Two direct lookup patterns:
    /{card_id}         → lookup by card primary key (set+number+optional suffix)
    /{set_id}/{number} → lookup by set/number combination
- Export endpoints:
    /export            → paginated JSON export
    /export.ndjson     → streaming NDJSON export for large datasets

⚠️ Security note:
- No authentication is enforced here.
- In production, you should restrict or proxy access.
"""

from __future__ import annotations
from typing import Optional, Dict, Any, List

import json
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_
from sqlmodel import Session, select

from services.shared.database import get_session
from services.shared.models import User
from opama_pokemon_tcg.catalog.models import Set, Card
from opama_pokemon_tcg.inventory.models import InventoryItem
from services.auth.middleware import get_current_user
from services.auth.org_context import OrgContext, get_current_org

# Router is mounted in main.py with prefix="/cards"
router = APIRouter(tags=["cards"])


# ---------------------------------------------------------------------------
# Sets
# ---------------------------------------------------------------------------


@router.get("/sets")
def list_sets(session: Session = Depends(get_session)):
    """
    Return all sets in the database.

    Includes: id, name, series, legality, etc.
    Useful for populating dropdowns, lists, or metadata browsers.
    """
    return session.exec(select(Set)).all()


# ---------------------------------------------------------------------------
# Collection completion (per-set progress) — org-scoped
# Declared before the dynamic /{set_id}/{number} route so they aren't shadowed.
# ---------------------------------------------------------------------------


@router.get("/sets/progress")
def sets_progress(
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(get_current_org),
):
    """Per-set collection progress for the active organization.

    Denominator is the number of cards the catalog holds for each set (the
    official `Set.total` is only populated after a live sync, so it's surfaced as
    `official_total` for reference). Only sets the org owns cards in are returned.
    """
    catalog_counts = dict(
        session.exec(select(Card.set_id, func.count()).group_by(Card.set_id)).all()
    )
    owned = dict(
        session.exec(
            select(Card.set_id, func.count(func.distinct(InventoryItem.card_id)))
            .select_from(InventoryItem)
            .join(Card, Card.id == InventoryItem.card_id)
            .where(InventoryItem.org_id == ctx.org_id)
            .group_by(Card.set_id)
        ).all()
    )
    sets = {s.id: s for s in session.exec(select(Set).where(Set.id.in_(list(owned.keys())))).all()}

    rows = []
    for sid, n_owned in owned.items():
        s = sets.get(sid)
        total = catalog_counts.get(sid, 0)
        rows.append({
            "set_id": sid,
            "name": s.name if s else sid,
            "series": s.series if s else None,
            "release_date": s.release_date if s else None,
            "owned": n_owned,
            "total": total,
            "official_total": (s.total if s else None),
            "pct": round(100 * n_owned / total, 1) if total else 0.0,
        })
    rows.sort(key=lambda r: (-r["pct"], -r["owned"]))

    return {
        "summary": {
            "sets_started": len(rows),
            "cards_owned": sum(r["owned"] for r in rows),
            "catalog_total": sum(catalog_counts.values()),
        },
        "sets": rows,
    }


@router.get("/sets/{set_id}/missing")
def set_missing_cards(
    set_id: str,
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(get_current_org),
):
    """The cards in a set the active org does NOT own yet (the want-list view)."""
    owned_ids = set(
        session.exec(
            select(InventoryItem.card_id)
            .select_from(InventoryItem)
            .join(Card, Card.id == InventoryItem.card_id)
            .where(InventoryItem.org_id == ctx.org_id, Card.set_id == set_id)
        ).all()
    )
    cards = session.exec(
        select(Card).where(Card.set_id == set_id).order_by(Card.number_sort, Card.number)
    ).all()
    missing = [
        {
            "card_id": c.id, "name": c.name, "number": c.number,
            "rarity": c.rarity, "image_small": c.image_small,
        }
        for c in cards if c.id not in owned_ids
    ]
    return {
        "set_id": set_id,
        "total": len(cards),
        "owned": len(cards) - len(missing),
        "missing": missing,
    }


# ---------------------------------------------------------------------------
# Cards (basic listing)
# ---------------------------------------------------------------------------


@router.get("")
def list_cards(
    q: Optional[str] = Query(None, max_length=200, description="Substring match on card name"),
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_session),
):
    """
    Return a list of cards (lightweight endpoint for autocomplete).

    Query params:
    - q: optional substring match against card name (ILIKE).
    - limit: restricts the number of returned rows (1–500).

    Example:
      GET /cards?q=pikachu&limit=10
    """
    stmt = select(Card)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Card.name.ilike(like))
    stmt = stmt.limit(limit)
    return session.exec(stmt).all()


# ---------------------------------------------------------------------------
# Search (keep above dynamic routes to avoid shadowing)
# ---------------------------------------------------------------------------


@router.get("/search")
def search_cards(
    q: Optional[str] = Query(None, max_length=200, description="Match against name, id, or number"),
    set_id: Optional[str] = Query(
        None, description="Restrict results to a set code (e.g., 'sv10')"
    ),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    """
    Paginated card search.

    Filters:
    - q → searches name, id, or printed number (ILIKE).
    - set_id → restricts search to a single set.

    Returns:
    - total: total count of matches
    - items: current page of cards

    Results are ordered by set_id and number for stable sorting.
    """
    filters: List[Any] = []
    if q:
        like = f"%{q}%"
        filters.append(
            or_(Card.name.ilike(like), Card.id.ilike(like), Card.number.ilike(like))
        )
    if set_id:
        filters.append(Card.set_id == set_id)

    # Total count for pagination
    total = session.exec(select(func.count()).select_from(Card).where(*filters)).one()

    # Current page of items
    items = session.exec(
        select(Card)
        .where(*filters)
        .order_by(Card.set_id, Card.number_sort, Card.number)
        .offset(offset)
        .limit(limit)
    ).all()

    return {"total": int(total or 0), "items": items}


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------


def serialize_card_obj(c: Card) -> Dict[str, Any]:
    """
    Serialize a Card object into a minimal JSON-friendly dict.

    Keep output schema stable for use by external tools (ETL, CSV, NDJSON).
    Includes card identity + key playability attributes.
    """
    return {
        "id": c.id,
        "name": c.name,
        "set_id": c.set_id,
        "number": getattr(c, "number", None),
        "types": getattr(c, "types", None),
        "subtypes": getattr(c, "subtypes", None),
        "supertype": getattr(c, "supertype", None),
        "rarity": getattr(c, "rarity", None),
        "hp": getattr(c, "hp", None),
        "retreat_cost": getattr(c, "retreat_cost", None),
        "ability_name": getattr(c, "ability_name", None),
        "ability_text": getattr(c, "ability_text", None),
        "attack1_name": getattr(c, "attack1_name", None),
        "attack1_text": getattr(c, "attack1_text", None),
        "attack1_damage": getattr(c, "attack1_damage", None),
        "attack2_name": getattr(c, "attack2_name", None),
        "attack2_text": getattr(c, "attack2_text", None),
        "attack2_damage": getattr(c, "attack2_damage", None),
        "attack3_name": getattr(c, "attack3_name", None),
        "attack3_text": getattr(c, "attack3_text", None),
        "attack3_damage": getattr(c, "attack3_damage", None),
    }


@router.get("/export")
def cards_export(
    limit: int = Query(5000, ge=500, le=20000, description="Max rows per page"),
    cursor: Optional[str] = Query(None, description="Resume export after last id"),
    session: Session = Depends(get_session),
):
    """
    Paginated JSON export of the card catalog.

    Query params:
    - limit: max rows per page (500–20000).
    - cursor: last id from previous page (for resuming).

    Response:
    - items: serialized card dicts
    - next: cursor for next page (None if no more results)

    Example:
      GET /cards/export?limit=1000
    """
    stmt = select(Card).order_by(Card.id).limit(limit + 1)
    if cursor:
        stmt = stmt.where(Card.id > cursor)

    rows = session.exec(stmt).all()
    items = [serialize_card_obj(r) for r in rows[:limit]]
    next_cursor = rows[-1].id if len(rows) > limit else None
    return {"items": items, "next": next_cursor}


@router.get("/export.ndjson")
def cards_export_ndjson(
    session: Session = Depends(get_session),
    chunk: int = Query(5000, ge=500, le=20000, description="Chunk size per DB page"),
):
    """
    Streaming NDJSON export (newline-delimited JSON).

    - Each card is output as one line of JSON.
    - Designed for large datasets (pipe into ETL tools, jq, etc.).
    - Streams in chunks to avoid memory blowup.

    ⚠️ DB session is reused inside the generator — ensure your dependency
    lifecycle allows long-running streams. Otherwise, create a fresh
    session per chunk inside `gen()`.
    """

    def gen():
        last_id: Optional[str] = None
        while True:
            stmt = select(Card).order_by(Card.id).limit(chunk)
            if last_id:
                stmt = stmt.where(Card.id > last_id)

            batch = session.exec(stmt).all()
            if not batch:
                break

            for c in batch:
                yield json.dumps(serialize_card_obj(c), ensure_ascii=False) + "\n"

            last_id = batch[-1].id

    return StreamingResponse(gen(), media_type="application/x-ndjson")


# ---------------------------------------------------------------------------
# Catalog Synchronization (Manual Triggers)
# ---------------------------------------------------------------------------


@router.post("/sync/trigger")
def trigger_catalog_sync(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Manually trigger a full catalog synchronization.

    This endpoint:
    - Discovers new sets from the Pokemon TCG API
    - Syncs any sets not yet in the database
    - Returns immediately with a task ID for tracking

    The actual sync runs asynchronously via Celery.

    Returns:
        - message: Confirmation message
        - sync_type: "manual"
        - sets_discovered: Number of new sets found (if available)
    """
    from opama_pokemon_tcg.catalog.sync_service import CatalogSyncService

    try:
        # Check for new sets synchronously
        service = CatalogSyncService(session)
        new_sets = service.discover_new_sets()

        if not new_sets:
            return {
                "message": "No new sets to sync",
                "sync_type": "manual",
                "sets_discovered": 0,
                "new_sets": []
            }

        # Trigger async sync
        # Note: In production with Celery, use:
        # from celery_app import check_and_sync_catalog_task
        # task = check_and_sync_catalog_task.delay()
        # return {"task_id": task.id, "sets_discovered": len(new_sets)}

        # For now, run synchronously
        log = service.create_sync_log('manual')
        log.sets_discovered = len(new_sets)

        success_count = 0
        fail_count = 0

        for set_id in new_sets:
            success = service.sync_set(set_id)
            if success:
                success_count += 1
            else:
                fail_count += 1

        log.sets_synced = success_count
        log.sets_failed = fail_count
        status = 'success' if fail_count == 0 else 'partial' if success_count > 0 else 'failed'
        service.finalize_sync_log(log, status)

        return {
            "message": "Catalog sync completed",
            "sync_type": "manual",
            "sync_log_id": log.id,
            "sets_discovered": len(new_sets),
            "sets_synced": success_count,
            "sets_failed": fail_count,
            "status": status,
            "new_sets": new_sets
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@router.post("/sync/set/{set_id}")
def sync_specific_set(
    set_id: str = Path(..., description="Set ID to sync (e.g., 'me1', 'sv10')"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Manually sync a specific set.

    Useful for:
    - Re-syncing a set that failed
    - Updating an existing set with new cards
    - Testing sync functionality

    Args:
        set_id: Pokemon TCG set ID (e.g., "me1")

    Returns:
        - set_id: The set that was synced
        - success: Whether sync succeeded
        - cards_count: Number of cards synced
    """
    from opama_pokemon_tcg.catalog.sync_service import CatalogSyncService

    try:
        service = CatalogSyncService(session)
        success = service.sync_set(set_id)

        if not success:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to sync set {set_id}"
            )

        # Get sync status
        from opama_pokemon_tcg.catalog.models import SetSyncStatus
        sync_status = session.get(SetSyncStatus, set_id)

        return {
            "set_id": set_id,
            "success": True,
            "cards_count": sync_status.cards_count if sync_status else 0,
            "last_synced_at": sync_status.last_synced_at.isoformat() if sync_status else None
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sync/status")
def get_sync_status(
    limit: int = Query(1, ge=1, le=50, description="Number of recent syncs to return"),
    session: Session = Depends(get_session)
):
    """
    Get recent sync status/history.

    Returns information about the most recent catalog synchronizations:
    - When they ran
    - How many sets were synced
    - Success/failure status
    - Error messages if any

    Args:
        limit: Number of recent syncs to return (default: 1)

    Returns:
        List of sync log entries, newest first
    """
    from opama_pokemon_tcg.catalog.models import CatalogSyncLog

    logs = session.exec(
        select(CatalogSyncLog)
        .order_by(CatalogSyncLog.started_at.desc())
        .limit(limit)
    ).all()

    if not logs:
        return {"message": "No sync history yet", "syncs": []}

    return {
        "syncs": [
            {
                "id": log.id,
                "sync_type": log.sync_type,
                "started_at": log.started_at.isoformat(),
                "completed_at": log.completed_at.isoformat() if log.completed_at else None,
                "status": log.status,
                "sets_discovered": log.sets_discovered,
                "sets_synced": log.sets_synced,
                "sets_failed": log.sets_failed,
                "error_message": log.error_message
            }
            for log in logs
        ],
        "count": len(logs)
    }


@router.get("/sync/sets")
def get_set_sync_status(
    session: Session = Depends(get_session)
):
    """
    Get synchronization status for all sets.

    Returns information about which sets have been synced:
    - Set ID
    - Last sync time
    - Number of cards
    - Sync status (success/failed)

    Useful for:
    - Monitoring which sets are up to date
    - Identifying sets that need re-syncing
    - Troubleshooting sync issues
    """
    from opama_pokemon_tcg.catalog.models import SetSyncStatus

    statuses = session.exec(
        select(SetSyncStatus)
        .order_by(SetSyncStatus.last_synced_at.desc())
    ).all()

    return {
        "sets": [
            {
                "set_id": status.set_id,
                "last_synced_at": status.last_synced_at.isoformat(),
                "cards_count": status.cards_count,
                "sync_status": status.sync_status,
                "error_details": status.error_details
            }
            for status in statuses
        ],
        "count": len(statuses)
    }


# ---------------------------------------------------------------------------
# Direct lookups (dynamic paths) — keep last to avoid shadowing /search etc.
# ---------------------------------------------------------------------------


@router.get("/{card_id}")
def get_card_by_id(
    card_id: str = Path(
        ...,
        pattern=r"^[a-z0-9]+-[a-z0-9]+[a-z]?$",  # e.g. "sv10-49", "sv9-12a"
        description="Card primary key (set+number+suffix).",
    ),
    session: Session = Depends(get_session),
):
    """
    Lookup a card by its primary key (set_id + number + optional letter).
    """
    c = session.get(Card, card_id)
    if not c:
        raise HTTPException(status_code=404, detail="Not Found")
    return c


@router.get("/{set_id}/{number}")
def get_card_by_set_and_number(
    set_id: str = Path(
        ..., pattern=r"^[a-z0-9]+$", description="Set code, e.g. 'sv10'"
    ),
    number: str = Path(
        ..., pattern=r"^[0-9]+[a-z]?$", description="Card number, e.g. '49' or '49a'"
    ),
    session: Session = Depends(get_session),
):
    """
    Lookup a card by (set_id, printed number).
    """
    c = session.exec(
        select(Card).where(Card.set_id == set_id, Card.number == number)
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Not Found")
    return c
