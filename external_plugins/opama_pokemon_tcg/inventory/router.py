# services/inventory/router.py
"""
Inventory Service - Collection Management API
----------------------------------------------
Endpoints to add, list, edit, bulk import/export, and quick-add inventory.

This service manages user-owned card collections with detailed metadata.

Highlights:
- Merge-on-duplicate: adding the same (user, card, condition, flags) increments qty.
- CSV import supports flexible booleans (1/true/yes).
- Quick-add parser accepts compact notations like "12x2", "GG10 3", "12 RH".

Security:
- Authentication required on all write operations (enforced via get_current_user).
- Ownership validation prevents unauthorized access to other users' inventory.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select
from services.shared.database import get_session
from services.auth.middleware import get_current_user
from services.auth.org_context import OrgContext, get_current_org
from services.shared.models import User
from opama_pokemon_tcg.inventory.models import InventoryItem
from opama_pokemon_tcg.catalog.models import Card, Set
import re
import csv
import io
from io import StringIO

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class InventoryIn(BaseModel):
    """
    Payload to add a single inventory row.
    If an existing row matches on (user_id, card_id, condition, flags),
    quantity is incremented instead of creating a duplicate row.

    Note: user_id is now inferred from authentication token.
          For demo/testing, user_id can still be provided explicitly.

    # TODO(validation): Consider constraining `condition` to enums ("NM","LP",...)
                        and validating currency to ISO-4217 codes.
    """

    user_id: Optional[int] = None  # Optional: inferred from auth token if not provided
    card_id: str
    quantity: int = 1
    condition: str | None = None
    is_holo: bool | None = None
    is_reverse_holo: bool | None = None
    is_alt_art: bool | None = None
    notes: str | None = None
    acquired_from: str | None = None
    purchase_price: float | None = None
    currency: str | None = None


class QuickAddIn(BaseModel):
    """
    Bulk "quick add" by card numbers within a set.

    Examples:
      ["12", "12x2", "12 (2)", "12 2", "12 - 2", "102 RH", "GG10 3", "201/182 NM"]

    Parsing rules:
      - "xN", "(N)", or trailing " - N"/" N" set quantity.
      - "RH" sets reverse holo.
      - End tokens "NM|LP|MP|HP|DMG|PSA\\d+" override per-line condition.
      - Alphanumeric numbers (e.g., "GG10") and fraction numbers ("201/182") are kept.

    Note: user_id is now inferred from authentication token.
          For demo/testing, user_id can still be provided explicitly.

    # TODO(ux): Support more flags: "H" (holo), "AA" (alt art), foil markers per set.
    """

    user_id: Optional[int] = None  # Optional: inferred from auth token if not provided
    set_id: str  # e.g., "sv9"
    entries: List[str]  # e.g., ["12", "34x2", "102 RH", "GG10 3"]
    condition: Optional[str] = None  # default condition (can be overridden per line)
    dry_run: bool = False


class InventoryUpdate(BaseModel):
    """
    Payload to update an inventory item.
    All fields are optional - only provided fields will be updated.
    """

    quantity: Optional[int] = None
    quantity_delta: Optional[int] = None
    purchase_price_per_card: Optional[float] = None
    currency: Optional[str] = None
    acquired_from: Optional[str] = None
    notes: Optional[str] = None
    condition: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def parse_entry(e: str):
    """
    Parse a single quick-add entry into components.

    Returns:
        (number_str, qty:int, per_line_condition:str|None, flags:dict)

    Supported inputs:
        "12" ; "12x2" ; "12 2" ; "12 (2)" ; "12 - 2"
        "12 RH" (reverse holo) ; "102 NM" ; "GG10 3"

    # TODO(parsing): Add support for "AA" (alt art), "H" (holo), and other set-specific
                    suffixes like "TG", "CSR" if those appear in number fields.
    """
    s = e.strip()
    qty = 1
    per_cond = None
    flags = {"is_reverse_holo": False, "is_holo": None, "is_alt_art": None}

    # Reverse holo flag extraction (case-insensitive whole-word "RH")
    if re.search(r"\bRH\b", s, re.I):
        flags["is_reverse_holo"] = True
        s = re.sub(r"\bRH\b", "", s, flags=re.I).strip()

    # Quantity patterns at end: "xN", "(N)", " - N" or " N"
    m = (
        re.search(r"x\s*(\d+)$", s, re.I)
        or re.search(r"\(\s*(\d+)\s*\)$", s)
        or re.search(r"[-\s](\d+)$", s)
    )
    if m:
        qty = int(m.group(1))
        s = s[: m.start()].strip()

    # Optional condition token at end ("NM", "LP", ... or "PSA10")
    m = re.search(r"(NM|LP|MP|HP|DMG|PSA\d+)$", s, re.I)
    if m:
        per_cond = m.group(1).upper()
        s = s[: m.start()].strip()

    number_str = s  # Preserve letters/fractions: "GG10", "201/182", etc.
    return number_str, qty, per_cond, flags


def _merge_or_create_inventory(
    session: Session,
    *,
    org_id: int,
    user_id: int,
    card_id: str,
    quantity: int,
    condition: Optional[str],
    is_holo: Optional[bool],
    is_reverse_holo: Optional[bool],
    is_alt_art: Optional[bool],
    **rest,
) -> InventoryItem:
    """
    Merge-on-duplicate behavior (pool tenancy):
      - If an existing row in the active org matches
        (org_id, card_id, condition, flags), increment its quantity.
      - Otherwise, create a new row owned by the org. user_id is retained as the
        acting/created-by actor for audit.

    # TODO(db): Add a DB UNIQUE INDEX on
                (org_id, card_id, condition, is_holo, is_reverse_holo, is_alt_art)
                to enforce this invariant at the database layer and prevent races.
    """
    existing = session.exec(
        select(InventoryItem).where(
            (InventoryItem.org_id == org_id)
            & (InventoryItem.card_id == card_id)
            & (InventoryItem.condition == condition)
            & (InventoryItem.is_holo.is_(is_holo))
            & (InventoryItem.is_reverse_holo.is_(is_reverse_holo))
            & (InventoryItem.is_alt_art.is_(is_alt_art))
        )
    ).first()

    if existing:
        # Defensive int coercion; treat None as 0 to avoid TypeErrors
        existing.quantity = int((existing.quantity or 0) + (quantity or 0))
        session.add(existing)
        return existing

    # Create new row; only persist whitelisted optional fields from `rest`
    inv = InventoryItem(
        org_id=org_id,          # owning organization (tenancy/RLS scope)
        user_id=user_id,        # creating/acting user (audit)
        card_id=card_id,
        quantity=quantity,
        condition=condition,
        is_holo=is_holo,
        is_reverse_holo=is_reverse_holo,
        is_alt_art=is_alt_art,
        **{
            k: v
            for k, v in rest.items()
            if k in {"notes", "acquired_from", "purchase_price", "currency"}
        },
    )
    session.add(inv)
    return inv


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/quick_add")
def quick_add_inventory(
    payload: QuickAddIn,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    ctx: OrgContext = Depends(get_current_org),
):
    """
    Quickly add many cards by set + number strings.

    Authentication: REQUIRED - Uses Firebase token to identify user.

    Flow:
      1) Load set and its cards for O(1) lookups by printed number.
      2) Parse each entry; resolve a card; build a result preview row.
      3) If dry_run=False, merge/create inventory rows and commit once.

    Returns:
      {
        ok: bool,
        inserted: int,      # number of rows merged/created (0 on dry_run)
        preview: [...],     # parsed/normalized entries
        errors:  [...]      # entries that failed to resolve
      }

    # TODO(perf): If `entries` can be >10k, consider chunking + periodic commits
                 to limit transaction size and memory pressure.
    """
    # Always use authenticated user's ID
    target_user_id = current_user.id

    # Validate set presence
    s = session.get(Set, payload.set_id)
    if not s:
        raise HTTPException(
            404, f"Set {payload.set_id} not found. Import the set CSV first."
        )

    results = []
    errors = []
    to_upsert: List[InventoryItem] = []

    # Preload cards in the set → map by normalized printed number
    cards = session.exec(select(Card).where(Card.set_id == payload.set_id)).all()
    by_number = {(c.number or "").strip().upper(): c for c in cards}

    for raw in payload.entries:
        number_str, qty, per_cond, flags = parse_entry(raw)
        key = number_str.strip().upper()

        c = by_number.get(key)
        if not c:
            # Fallback: if digits-only, try prefix match for fraction numbers "12"→"12/198"
            if key.isdigit():
                for n, cand in by_number.items():
                    if n.startswith(key):
                        c = cand
                        break

        if not c:
            errors.append(
                {"entry": raw, "reason": "No card with that number in this set"}
            )
            continue

        result_row = {
            "entry": raw,
            "card_id": c.id,
            "name": c.name,
            "number": c.number,
            "set_id": c.set_id,
            "qty": qty,
            "condition": (per_cond or payload.condition),
            **flags,
        }
        results.append(result_row)

        if not payload.dry_run:
            inv = _merge_or_create_inventory(
                session,
                org_id=ctx.org_id,
                user_id=target_user_id,
                card_id=c.id,
                quantity=qty,
                condition=(per_cond or payload.condition),
                # Flags beyond RH default to None (unknown) unless parser expands
                is_holo=None,
                is_reverse_holo=flags["is_reverse_holo"],
                is_alt_art=None,
            )
            to_upsert.append(inv)

    if not payload.dry_run and to_upsert:
        session.commit()  # single commit for all merges/creates

    return {
        "ok": True,
        "inserted": 0 if payload.dry_run else len(to_upsert),
        "preview": results,
        "errors": errors,
    }


@router.post("")
def add_inventory(
    item: InventoryIn,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    ctx: OrgContext = Depends(get_current_org),
):
    """
    Add a single inventory entry.
    If a matching row exists (user_id, card_id, condition, flags), increments quantity.

    Authentication: REQUIRED - Uses Firebase token to identify user.

    Response:
      {"id": <inventory_id>, "merged": True}

    # TODO(api): Return `merged=False` when a new row is created to distinguish paths.
    """
    # Always use authenticated user's ID
    target_user_id = current_user.id

    # Validate the card FK
    card = session.get(Card, item.card_id)
    if not card:
        raise HTTPException(
            404, f"Card {item.card_id} not found in catalog. Import set CSV first."
        )

    # Override user_id from auth (ignore any user_id in payload); scope to active org
    item_data = item.dict()
    item_data["user_id"] = target_user_id
    item_data["org_id"] = ctx.org_id

    inv = _merge_or_create_inventory(session, **item_data)
    session.commit()
    session.refresh(inv)
    return {"id": inv.id, "merged": True}


@router.get("")
def list_inventory(
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(get_current_org),
):
    """Return raw InventoryItem rows for the active organization (no card join)."""
    return session.exec(
        select(InventoryItem).where(InventoryItem.org_id == ctx.org_id)
    ).all()


@router.get("/with_cards")
def list_inventory_with_cards(
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(get_current_org),
):
    """
    Return inventory rows joined with selected Card fields for UI display.
    Authentication: REQUIRED. Scoped to the active organization.
    """
    items = session.exec(
        select(InventoryItem).where(InventoryItem.org_id == ctx.org_id)
    ).all()
    card_ids = list({i.card_id for i in items})
    cards = {
        c.id: c for c in session.exec(select(Card).where(Card.id.in_(card_ids))).all()
    }

    def pick(c: Card) -> dict:
        return {
            "id": c.id,
            "name": c.name,
            "set_id": c.set_id,
            "number": c.number,
            "rarity": c.rarity,
            "image_small": c.image_small,
            "image_large": c.image_large,
            # Common client filter fields:
            "types": c.types,
            "subtypes": c.subtypes,
            "hp": c.hp,
            "ability_name": c.ability_name,
            "ability_text": c.ability_text,
            "attack1_damage": c.attack1_damage,
            "attack2_damage": c.attack2_damage,
            "attack3_damage": c.attack3_damage,
            "weaknesses": c.weaknesses,
            "resistances": c.resistances,
            "retreat_cost": c.retreat_cost,
            "stage": c.stage,
        }

    return [
        {"inventory": i, "card": pick(cards[i.card_id]) if i.card_id in cards else None}
        for i in items
    ]


MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

@router.post("/bulk")
async def import_inventory_csv(
    file: UploadFile,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    ctx: OrgContext = Depends(get_current_org),
):
    """
    Import inventory from CSV.

    Authentication: REQUIRED - Uses Firebase token to identify user.

    Expected columns (case-insensitive):
      card_id,quantity,condition,is_holo,is_reverse_holo,is_alt_art,
      notes,acquired_from,purchase_price,currency

    Behavior:
    - Skips unknown card_ids (assumes catalog imported first).
    - Coerces booleans from 1/true/yes.
    - Merges duplicates by (user_id, card_id, condition, flags).

    # TODO(resilience): Add transaction chunking and report per-row errors
                        back to the client (row index, reason).
    """
    target_user_id = current_user.id
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large (max 10 MB)")
    f = io.StringIO(data.decode("utf-8"))
    reader = csv.DictReader(f)
    count = 0

    for r in reader:
        cid = (r.get("card_id") or "").strip()
        if not cid:
            continue
        if not session.get(Card, cid):
            # Unknown card → skip; caller can reconcile later
            continue

        _merge_or_create_inventory(
            session,
            org_id=ctx.org_id,
            user_id=target_user_id,
            card_id=cid,
            quantity=max(1, int(r.get("quantity") or 1)),
            condition=r.get("condition"),
            is_holo=(str(r.get("is_holo") or "").lower() in ("1", "true", "yes")),
            is_reverse_holo=(
                str(r.get("is_reverse_holo") or "").lower() in ("1", "true", "yes")
            ),
            is_alt_art=(str(r.get("is_alt_art") or "").lower() in ("1", "true", "yes")),
            notes=r.get("notes"),
            acquired_from=r.get("acquired_from"),
            purchase_price=(
                float(r.get("purchase_price")) if r.get("purchase_price") else None
            ),
            currency=r.get("currency"),
        )
        count += 1

    session.commit()
    return {"imported": count}


@router.patch("/{item_id}")
def update_inventory_item(
    item_id: int,
    updates: InventoryUpdate,
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(get_current_org),
):
    """
    Update an inventory item's fields.

    Authentication: REQUIRED - can only update own inventory items.

    Supports:
    - quantity: Set absolute quantity
    - quantity_delta: Adjust quantity by delta (+/-)
    - purchase_price_per_card: Set purchase price
    - currency: Set currency (USD, EUR, etc.)
    - acquired_from: Set where acquired
    - notes: Set notes
    - condition: Update condition

    If resulting quantity <= 0, the row is deleted.
    """
    inv = session.get(InventoryItem, item_id)
    if not inv:
        raise HTTPException(404, "Inventory item not found")

    # Org-scope validation
    if inv.org_id != ctx.org_id:
        raise HTTPException(403, "Cannot update another organization's inventory item")

    # Update quantity
    if updates.quantity is not None:
        inv.quantity = int(updates.quantity)
    if updates.quantity_delta is not None:
        inv.quantity = int((inv.quantity or 0) + updates.quantity_delta)

    # Update other fields if provided
    if updates.purchase_price_per_card is not None:
        inv.purchase_price_per_card = updates.purchase_price_per_card
    if updates.currency is not None:
        inv.currency = updates.currency
    if updates.acquired_from is not None:
        inv.acquired_from = updates.acquired_from
    if updates.notes is not None:
        inv.notes = updates.notes
    if updates.condition is not None:
        inv.condition = updates.condition

    # Delete if quantity is zero or negative
    if inv.quantity <= 0:
        session.delete(inv)
        session.commit()
        return {"deleted": True, "id": item_id}

    session.add(inv)
    session.commit()
    session.refresh(inv)
    return {"deleted": False, "item": inv}


@router.delete("/{item_id}")
def delete_inventory_item(
    item_id: int,
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(get_current_org),
):
    """
    Delete an inventory row by id.

    Authentication: REQUIRED - can only delete the active org's inventory items.
    """
    inv = session.get(InventoryItem, item_id)
    if not inv:
        raise HTTPException(404, "Inventory item not found")

    # Org-scope validation
    if inv.org_id != ctx.org_id:
        raise HTTPException(403, "Cannot delete another organization's inventory item")

    session.delete(inv)
    session.commit()
    return {"ok": True, "id": item_id}


@router.get("/export.csv")
def export_inventory_csv(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    ctx: OrgContext = Depends(get_current_org),
):
    """
    Export the active organization's inventory as CSV, joined with Card fields.

    Authentication: REQUIRED - exports only the active organization's inventory.

    Columns:
      inventory_id, card_id, name, set_id, number, rarity, types, subtypes, stage, hp,
      quantity, condition, is_holo, is_reverse_holo, is_alt_art, notes, acquired_from,
      purchase_price, currency

    # TODO(perf): For very large exports, consider server-side temp file
                  generation and returning a pre-signed URL instead of streaming
                  from memory. Also consider chunked queries.
    """
    items = session.exec(
        select(InventoryItem).where(InventoryItem.org_id == ctx.org_id)
    ).all()
    if not items:
        # Still return a CSV with only the header
        items = []

    card_ids = list({i.card_id for i in items})
    cards = {
        c.id: c for c in session.exec(select(Card).where(Card.id.in_(card_ids))).all()
    }

    out = StringIO()
    fieldnames = [
        "inventory_id",
        "card_id",
        "name",
        "set_id",
        "number",
        "rarity",
        "types",
        "subtypes",
        "stage",
        "hp",
        "quantity",
        "condition",
        "is_holo",
        "is_reverse_holo",
        "is_alt_art",
        "notes",
        "acquired_from",
        "purchase_price_per_card",
        "currency",
    ]
    writer = csv.DictWriter(out, fieldnames=fieldnames)
    writer.writeheader()

    for it in items:
        c = cards.get(it.card_id)
        writer.writerow(
            {
                "inventory_id": it.id,
                "card_id": it.card_id,
                "name": (c.name if c else None),
                "set_id": (c.set_id if c else None),
                "number": (c.number if c else None),
                "rarity": (c.rarity if c else None),
                "types": (c.types if c else None),
                "subtypes": (c.subtypes if c else None),
                "stage": (c.stage if c else None),
                "hp": (c.hp if c else None),
                "quantity": it.quantity,
                "condition": it.condition,
                "is_holo": it.is_holo,
                "is_reverse_holo": it.is_reverse_holo,
                "is_alt_art": it.is_alt_art,
                "notes": it.notes,
                "acquired_from": it.acquired_from,
                "purchase_price_per_card": it.purchase_price_per_card,
                "currency": it.currency,
            }
        )

    out.seek(0)
    filename = f"inventory_user_{current_user.id}.csv"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(out, media_type="text/csv", headers=headers)


# REMOVED: /backup/db endpoint - SECURITY RISK
# This endpoint allowed unauthenticated database download and has been removed.
# For database backups, use proper backup tools (pg_dump, sqlite3 .backup, etc.)
# with appropriate access controls and encryption.
