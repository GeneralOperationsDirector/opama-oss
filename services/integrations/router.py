"""
OpenClaw Integration Router
----------------------------
Internal API endpoints called by the OpenClaw opama agent. Authenticated
via X-OpenClaw-Token header (shared secret) rather than Firebase JWT, since
this is a local agent-to-backend call, not an end-user request.

All endpoints operate on behalf of the user identified by OPENCLAW_USER_ID
(defaults to 1).

Endpoints:
  GET  /integrations/openclaw/catalog/search   — search card catalog
  GET  /integrations/openclaw/inventory        — list/search inventory
  POST /integrations/openclaw/inventory        — add card item(s) to inventory
  GET  /integrations/openclaw/portfolio        — portfolio value summary
  POST /integrations/openclaw/receipt          — parse receipt text/image
  POST /integrations/openclaw/describe         — AI-generate a listing description
  POST /integrations/openclaw/listings/draft   — draft marketplace listing copy
  POST /integrations/openclaw/identify         — identify any item (ISBN, barcode, image)
  GET  /integrations/openclaw/assets           — list/search generic assets
  POST /integrations/openclaw/assets           — add a generic asset
  GET  /integrations/openclaw/assets/{id}      — get single generic asset
  DELETE /integrations/openclaw/assets/{id}    — delete a generic asset
"""

from __future__ import annotations

import os
import base64
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel
from sqlmodel import Session, select, func

import json

from services.shared.database import get_session
from services.shared.models import User, GenericAsset

# Pokémon TCG is an optional external plugin (external_plugins/opama_pokemon_tcg/,
# see PLUGIN_PATHS) — not present in core-only deployments (e.g. oss-test stack).
# Endpoints that need it call _require_pokemon_tcg() to fail clearly when absent.
try:
    from opama_pokemon_tcg.catalog.models import Card
    from opama_pokemon_tcg.inventory.models import InventoryItem
except ImportError:
    Card = None
    InventoryItem = None

router = APIRouter(prefix="/integrations/openclaw", tags=["openclaw"])


def _require_pokemon_tcg():
    if Card is None or InventoryItem is None:
        raise HTTPException(503, "Pokémon TCG module is not installed on this instance")

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

_TOKEN = os.getenv("OPENCLAW_API_TOKEN", "")
_USER_ID = int(os.getenv("OPENCLAW_USER_ID", "1"))


def _auth(x_openclaw_token: str = Header(...)):
    if not _TOKEN:
        raise HTTPException(503, "OPENCLAW_API_TOKEN not configured on server")
    if x_openclaw_token != _TOKEN:
        raise HTTPException(401, "Invalid OpenClaw token")


def _get_agent_user(session: Session) -> User:
    user = session.get(User, _USER_ID)
    if not user:
        raise HTTPException(404, f"User {_USER_ID} not found (set OPENCLAW_USER_ID)")
    return user


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class InventoryAddItem(BaseModel):
    card_id: str
    quantity: int = 1
    condition: Optional[str] = None          # NM / LP / MP / HP / DMG
    is_holo: Optional[bool] = None
    is_reverse_holo: Optional[bool] = None
    is_alt_art: Optional[bool] = None
    grade: Optional[int] = None              # PSA/BGS grade 1-10
    grading_company: Optional[str] = None
    acquired_from: Optional[str] = None
    purchase_price_per_card: Optional[float] = None
    currency: Optional[str] = "CAD"
    notes: Optional[str] = None


class InventoryAddRequest(BaseModel):
    items: List[InventoryAddItem]


class ReceiptParseRequest(BaseModel):
    text: Optional[str] = None       # plain-text email body / receipt text
    image_url: Optional[str] = None  # publicly accessible image URL
    image_b64: Optional[str] = None  # base64-encoded image (fallback)
    source: Optional[str] = None     # "email" / "manual" / etc.


class DescribeRequest(BaseModel):
    name: str
    condition: Optional[str] = None
    set_name: Optional[str] = None
    notes: Optional[str] = None
    include_research: bool = False   # if True, agent should web-search first


class ListingDraftRequest(BaseModel):
    inventory_item_id: Optional[int] = None
    name: str
    condition: Optional[str] = None
    quantity: int = 1
    purchase_price: Optional[float] = None
    notes: Optional[str] = None
    platforms: List[str] = ["ebay", "kijiji", "facebook"]


class IdentifyRequest(BaseModel):
    image_url: Optional[str] = None
    image_b64: Optional[str] = None
    isbn: Optional[str] = None            # explicit ISBN bypass
    barcode: Optional[str] = None         # explicit barcode bypass
    hint: Optional[str] = None            # free-text hint ("this is a book")


class GenericAssetAddRequest(BaseModel):
    asset_class: str = "other"            # book / electronics / collectible / media / other
    name: str
    identifier: Optional[str] = None
    identifier_type: Optional[str] = None
    quantity: int = 1
    condition: Optional[str] = None
    purchase_price: Optional[float] = None
    currency: str = "CAD"
    acquired_from: Optional[str] = None
    asset_metadata: Optional[dict] = None  # author, publisher, model, etc.
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Catalog search
# ---------------------------------------------------------------------------

@router.get("/catalog/search")
def catalog_search(
    q: str = Query(..., max_length=200),
    set_id: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    session: Session = Depends(get_session),
    _: None = Depends(_auth),
):
    """Search the card catalog by name, id, or number."""
    _require_pokemon_tcg()
    stmt = select(Card)
    if set_id:
        stmt = stmt.where(Card.set_id == set_id)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            Card.name.ilike(pattern) | Card.id.ilike(pattern) | Card.number.ilike(pattern)
        )
    stmt = stmt.limit(limit)
    cards = session.exec(stmt).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "set_id": c.set_id,
            "number": c.number,
            "rarity": c.rarity,
            "supertype": c.supertype,
            "subtypes": c.subtypes,
            "image_small": c.image_small,
        }
        for c in cards
    ]


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

@router.get("/inventory")
def list_inventory(
    q: Optional[str] = Query(None, max_length=200),
    limit: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_session),
    _: None = Depends(_auth),
):
    """List the agent user's inventory, optionally filtered by card name."""
    _require_pokemon_tcg()
    stmt = (
        select(InventoryItem, Card)
        .join(Card, InventoryItem.card_id == Card.id)
        .where(InventoryItem.user_id == _USER_ID)
    )
    if q:
        stmt = stmt.where(Card.name.ilike(f"%{q}%"))
    stmt = stmt.limit(limit)

    rows = session.exec(stmt).all()
    return [
        {
            "inventory_id": item.id,
            "card_id": item.card_id,
            "name": card.name,
            "set_id": card.set_id,
            "number": card.number,
            "quantity": item.quantity,
            "condition": item.condition,
            "grade": item.grade,
            "grading_company": item.grading_company,
            "is_holo": item.is_holo,
            "is_reverse_holo": item.is_reverse_holo,
            "is_alt_art": item.is_alt_art,
            "purchase_price_per_card": item.purchase_price_per_card,
            "currency": item.currency,
            "acquired_from": item.acquired_from,
            "acquired_at": item.acquired_at,
            "notes": item.notes,
        }
        for item, card in rows
    ]


@router.post("/inventory")
def add_inventory(
    payload: InventoryAddRequest,
    session: Session = Depends(get_session),
    _: None = Depends(_auth),
):
    """
    Add one or more items to the agent user's inventory.
    Merges into existing row when (user_id, card_id, condition, grade, flags) match.
    """
    _require_pokemon_tcg()
    results = []
    for item in payload.items:
        card = session.get(Card, item.card_id)
        if not card:
            results.append({"card_id": item.card_id, "error": "card not found"})
            continue

        existing = session.exec(
            select(InventoryItem).where(
                InventoryItem.user_id == _USER_ID,
                InventoryItem.card_id == item.card_id,
                InventoryItem.condition == item.condition,
                InventoryItem.grade == item.grade,
                InventoryItem.is_holo == item.is_holo,
                InventoryItem.is_reverse_holo == item.is_reverse_holo,
                InventoryItem.is_alt_art == item.is_alt_art,
            )
        ).first()

        if existing:
            existing.quantity += max(1, item.quantity)
            if item.notes:
                existing.notes = item.notes
            session.add(existing)
            session.commit()
            session.refresh(existing)
            results.append({
                "card_id": item.card_id,
                "name": card.name,
                "inventory_id": existing.id,
                "merged": True,
                "quantity": existing.quantity,
            })
        else:
            new_item = InventoryItem(
                user_id=_USER_ID,
                card_id=item.card_id,
                quantity=max(1, item.quantity),
                condition=item.condition,
                is_holo=item.is_holo,
                is_reverse_holo=item.is_reverse_holo,
                is_alt_art=item.is_alt_art,
                grade=item.grade,
                grading_company=item.grading_company,
                acquired_from=item.acquired_from,
                acquired_at=datetime.utcnow() if item.acquired_from else None,
                purchase_price_per_card=item.purchase_price_per_card,
                currency=item.currency,
                notes=item.notes,
            )
            session.add(new_item)
            session.commit()
            session.refresh(new_item)
            results.append({
                "card_id": item.card_id,
                "name": card.name,
                "inventory_id": new_item.id,
                "merged": False,
                "quantity": new_item.quantity,
            })

    return {"added": len([r for r in results if "error" not in r]), "results": results}


# ---------------------------------------------------------------------------
# Portfolio summary
# ---------------------------------------------------------------------------

@router.get("/portfolio")
def portfolio_summary(
    session: Session = Depends(get_session),
    _: None = Depends(_auth),
):
    """Return a quick inventory count and estimated value summary."""
    _require_pokemon_tcg()
    total_items = session.exec(
        select(func.sum(InventoryItem.quantity))
        .where(InventoryItem.user_id == _USER_ID)
    ).one() or 0

    unique_cards = session.exec(
        select(func.count(InventoryItem.id))
        .where(InventoryItem.user_id == _USER_ID)
    ).one() or 0

    total_cost = session.exec(
        select(func.sum(InventoryItem.purchase_price_per_card * InventoryItem.quantity))
        .where(InventoryItem.user_id == _USER_ID)
        .where(InventoryItem.purchase_price_per_card.isnot(None))
    ).one() or 0.0

    return {
        "user_id": _USER_ID,
        "total_cards": int(total_items),
        "unique_cards": int(unique_cards),
        "total_cost_cad": round(float(total_cost), 2),
    }


# ---------------------------------------------------------------------------
# Receipt parsing
# ---------------------------------------------------------------------------

@router.post("/receipt")
async def parse_receipt(
    payload: ReceiptParseRequest,
    _: None = Depends(_auth),
):
    """
    Extract structured item data from a receipt (text or image).
    Text: gpt-oss:20b-cloud via local Ollama.
    Image: llava:7b via local Ollama (vision).
    """
    import httpx

    if not payload.text and not payload.image_url and not payload.image_b64:
        raise HTTPException(400, "Provide text, image_url, or image_b64")

    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")

    system = (
        "You are a receipt parser. Extract all purchased items from the provided receipt. "
        "Return ONLY valid JSON in this exact format with no other text:\n"
        '{"items": [{"name": "...", "quantity": 1, "unit_price": 0.00, "currency": "CAD", '
        '"notes": "..."}]}\n'
        "For Pokémon cards, include set name and card number in the name if visible. "
        "If currency is ambiguous, default to CAD. unit_price is per-unit cost."
    )

    if payload.image_url or payload.image_b64:
        # Use llava for vision
        if payload.image_url:
            # Fetch image bytes then base64-encode for Ollama
            async with httpx.AsyncClient() as hc:
                img_resp = await hc.get(payload.image_url, timeout=15)
            img_b64 = base64.b64encode(img_resp.content).decode()
        else:
            img_b64 = payload.image_b64

        ollama_body = {
            "model": "llava:7b",
            "prompt": f"{system}\n\nParse this receipt image and return the JSON.",
            "images": [img_b64],
            "stream": False,
            "format": "json",
        }
        endpoint = f"{ollama_url}/api/generate"
        response_key = "response"
    else:
        ollama_body = {
            "model": "gpt-oss:20b-cloud",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"Parse this receipt:\n\n{payload.text}"},
            ],
            "stream": False,
            "format": "json",
        }
        endpoint = f"{ollama_url}/api/chat"
        response_key = None  # use message.content

    try:
        async with httpx.AsyncClient(timeout=60) as hc:
            resp = await hc.post(endpoint, json=ollama_body)
            resp.raise_for_status()
            result = resp.json()

        if response_key:
            raw_text = result.get("response", "")
        else:
            raw_text = result.get("message", {}).get("content", "")

        raw_text = raw_text.strip()
        if raw_text.startswith("```"):
            raw_text = "\n".join(raw_text.split("\n")[1:])
            raw_text = raw_text.rsplit("```", 1)[0].strip()

        data = json.loads(raw_text)
        return {
            "source": payload.source or "unknown",
            "items": data.get("items", []),
            "raw_response": data,
        }
    except Exception as e:
        raise HTTPException(502, f"Receipt parsing failed: {e}")


# ---------------------------------------------------------------------------
# Item description generator
# ---------------------------------------------------------------------------

@router.post("/describe")
async def generate_description(
    payload: DescribeRequest,
    _: None = Depends(_auth),
):
    """
    Generate a marketplace-ready description via local Ollama (gpt-oss:20b-cloud).
    If include_research=True, the agent should web-search and pass findings as notes.
    """
    import httpx

    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")

    context_parts = [f"Item: {payload.name}"]
    if payload.condition:
        context_parts.append(f"Condition: {payload.condition}")
    if payload.set_name:
        context_parts.append(f"Set: {payload.set_name}")
    if payload.notes:
        context_parts.append(f"Additional context: {payload.notes}")

    prompt = (
        "\n".join(context_parts) + "\n\n"
        "Write a compelling, accurate marketplace listing for this item. "
        'Return JSON with keys: title (max 80 chars), description (2-3 paragraphs), '
        'condition_summary (1 sentence), suggested_keywords (list of 5-8 strings), '
        'price_note (string, empty if unknown).'
    )

    body = {
        "model": "gpt-oss:20b-cloud",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an expert marketplace listing writer specialising in "
                    "collectibles, trading cards, and physical goods. "
                    "Write honest, specific, buyer-focused descriptions. "
                    "Return ONLY valid JSON, no other text."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "format": "json",
    }

    try:
        async with httpx.AsyncClient(timeout=60) as hc:
            resp = await hc.post(f"{ollama_url}/api/chat", json=body)
            resp.raise_for_status()
        raw = resp.json().get("message", {}).get("content", "").strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:]).rsplit("```", 1)[0].strip()
        return json.loads(raw)
    except Exception as e:
        raise HTTPException(502, f"Description generation failed: {e}")


# ---------------------------------------------------------------------------
# Marketplace listing drafter
# ---------------------------------------------------------------------------

@router.post("/listings/draft")
async def draft_listing(
    payload: ListingDraftRequest,
    session: Session = Depends(get_session),
    _: None = Depends(_auth),
):
    """
    Draft marketplace listing copy for one or more platforms via local Ollama.
    Platforms supported: ebay, kijiji, facebook
    """
    import httpx

    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")

    # Optionally enrich from inventory record
    item_notes = payload.notes or ""
    if payload.inventory_item_id and InventoryItem is not None:
        inv = session.get(InventoryItem, payload.inventory_item_id)
        if inv:
            if inv.notes:
                item_notes = f"{inv.notes}. {item_notes}".strip(". ")
            if inv.purchase_price_per_card and not payload.purchase_price:
                payload.purchase_price = inv.purchase_price_per_card

    platform_guidelines = {
        "ebay": (
            "eBay: title max 80 chars, structured description with condition details, "
            "include shipping note 'Ships from Ontario, Canada'. "
            "Suggest a Buy It Now price in CAD."
        ),
        "kijiji": (
            "Kijiji: casual tone, clear price, local pickup available in Ontario. "
            "Short description (150 words max). Mention will not ship unless asked."
        ),
        "facebook": (
            "Facebook Marketplace: conversational, friendly. Include condition, "
            "price firm or OBO. Short — 3-5 sentences max."
        ),
    }

    selected = {p: platform_guidelines[p] for p in payload.platforms if p in platform_guidelines}
    if not selected:
        raise HTTPException(400, f"No valid platforms. Choose from: {list(platform_guidelines)}")

    prompt = (
        f"Item: {payload.name}\n"
        f"Condition: {payload.condition or 'Not specified'}\n"
        f"Quantity available: {payload.quantity}\n"
        f"Purchase price paid: {f'CAD ${payload.purchase_price:.2f}' if payload.purchase_price else 'unknown'}\n"
        f"Notes: {item_notes or 'none'}\n\n"
        "Write marketplace listings for each platform below. "
        "Return JSON with one key per platform name.\n\n"
        + "\n".join(f"- {g}" for g in selected.values())
    )

    body = {
        "model": "gpt-oss:20b-cloud",
        "messages": [
            {
                "role": "system",
                    "content": (
                        "You are an expert at writing marketplace listings for collectibles "
                        "and physical goods. Be specific, honest, and platform-appropriate. "
                        "Seller is based in Ontario, Canada. "
                        "Return ONLY valid JSON, no other text."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "format": "json",
        }

    try:
        async with httpx.AsyncClient(timeout=90) as hc:
            resp = await hc.post(f"{ollama_url}/api/chat", json=body)
            resp.raise_for_status()
        raw = resp.json().get("message", {}).get("content", "").strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:]).rsplit("```", 1)[0].strip()
        listings = json.loads(raw)
        return {
            "item": payload.name,
            "condition": payload.condition,
            "quantity": payload.quantity,
            "listings": listings,
        }
    except Exception as e:
        raise HTTPException(502, f"Listing draft failed: {e}")


# ---------------------------------------------------------------------------
# Item identifier — ISBN / barcode / image → enriched item info
# ---------------------------------------------------------------------------

@router.post("/identify")
async def identify_item(
    payload: IdentifyRequest,
    _: None = Depends(_auth),
):
    """
    Identify an item from an image or known identifier.

    Priority order:
      1. Explicit isbn/barcode → skip vision, go straight to lookup
      2. image_url / image_b64 → llava extracts identifiers, then lookup
      3. Fallback: return whatever llava described

    For books: queries Open Library API (no key needed).
    Returns a dict ready to pass to POST /assets.
    """
    import httpx

    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")

    isbn = payload.isbn
    barcode = payload.barcode
    vision_description: Optional[str] = None

    # --- Step 1: vision extraction if no explicit identifier ---
    if not isbn and not barcode and (payload.image_url or payload.image_b64):
        if payload.image_url:
            async with httpx.AsyncClient(timeout=15) as hc:
                img_resp = await hc.get(payload.image_url)
            img_b64 = base64.b64encode(img_resp.content).decode()
        else:
            img_b64 = payload.image_b64

        hint_text = f" The user says: {payload.hint}." if payload.hint else ""
        vision_prompt = (
            "Look at this image carefully."
            + hint_text
            + " Extract any identifiers you see: ISBN (13-digit number often starting with 978 or 979), "
            "barcode, serial number, model number, or product name. "
            "Also describe what the item is. "
            "Return ONLY valid JSON with keys: "
            '{"item_type": "book|electronics|collectible|media|other", '
            '"name": "...", "isbn": "..." or null, "barcode": "..." or null, '
            '"serial": "..." or null, "description": "...", '
            '"author": "..." or null, "publisher": "..." or null}'
        )
        try:
            async with httpx.AsyncClient(timeout=60) as hc:
                resp = await hc.post(
                    f"{ollama_url}/api/generate",
                    json={
                        "model": "llava:7b",
                        "prompt": vision_prompt,
                        "images": [img_b64],
                        "stream": False,
                        "format": "json",
                    },
                )
                resp.raise_for_status()
            raw = resp.json().get("response", "").strip()
            if raw.startswith("```"):
                raw = "\n".join(raw.split("\n")[1:]).rsplit("```", 1)[0].strip()
            vision_data = json.loads(raw)
            isbn = vision_data.get("isbn") or isbn
            barcode = vision_data.get("barcode") or barcode
            vision_description = vision_data.get("description")
        except Exception:
            vision_data = {}

    # --- Step 2: ISBN lookup via Open Library ---
    book_meta: dict = {}
    if isbn:
        isbn_clean = isbn.replace("-", "").replace(" ", "")
        try:
            async with httpx.AsyncClient(timeout=10) as hc:
                ol_resp = await hc.get(
                    "https://openlibrary.org/api/books",
                    params={
                        "bibkeys": f"ISBN:{isbn_clean}",
                        "format": "json",
                        "jscmd": "data",
                    },
                )
            ol_data = ol_resp.json()
            entry = ol_data.get(f"ISBN:{isbn_clean}", {})
            if entry:
                book_meta = {
                    "title": entry.get("title"),
                    "authors": [a.get("name") for a in entry.get("authors", [])],
                    "publishers": [p.get("name") for p in entry.get("publishers", [])],
                    "publish_date": entry.get("publish_date"),
                    "number_of_pages": entry.get("number_of_pages"),
                    "subjects": [s.get("name") for s in entry.get("subjects", [])[:5]],
                    "cover_url": entry.get("cover", {}).get("medium"),
                    "open_library_url": entry.get("url"),
                }
        except Exception:
            pass

    # --- Assemble result ---
    name = (
        book_meta.get("title")
        or (vision_data.get("name") if "vision_data" in dir() else None)
        or payload.hint
        or "Unknown item"
    )
    asset_class = "book" if (isbn or book_meta) else (
        vision_data.get("item_type", "other") if "vision_data" in dir() else "other"
    )
    metadata: dict = {}
    if book_meta:
        metadata.update(book_meta)
    if "vision_data" in dir():
        for k in ("author", "publisher", "serial"):
            if vision_data.get(k):
                metadata[k] = vision_data[k]
    if vision_description:
        metadata["vision_description"] = vision_description

    return {
        "asset_class": asset_class,
        "name": name,
        "identifier": isbn or barcode or None,
        "identifier_type": "isbn" if isbn else ("barcode" if barcode else None),
        "asset_metadata": metadata or None,
        "ready_to_add": True,
    }


# ---------------------------------------------------------------------------
# Generic asset inventory
# ---------------------------------------------------------------------------

@router.get("/assets")
def list_assets(
    q: Optional[str] = Query(None, max_length=200),
    asset_class: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_session),
    _: None = Depends(_auth),
):
    """List generic assets for the agent user, optionally filtered."""
    stmt = select(GenericAsset).where(GenericAsset.user_id == _USER_ID)
    if asset_class:
        stmt = stmt.where(GenericAsset.asset_class == asset_class)
    if q:
        stmt = stmt.where(GenericAsset.name.ilike(f"%{q}%"))
    stmt = stmt.order_by(GenericAsset.created_at.desc()).limit(limit)
    assets = session.exec(stmt).all()
    return [
        {
            "id": a.id,
            "asset_class": a.asset_class,
            "name": a.name,
            "identifier": a.identifier,
            "identifier_type": a.identifier_type,
            "quantity": a.quantity,
            "condition": a.condition,
            "purchase_price": a.purchase_price,
            "currency": a.currency,
            "acquired_from": a.acquired_from,
            "acquired_at": a.acquired_at,
            "asset_metadata": json.loads(a.asset_metadata) if a.asset_metadata else None,
            "notes": a.notes,
            "created_at": a.created_at,
        }
        for a in assets
    ]


@router.get("/assets/{asset_id}")
def get_asset(
    asset_id: int,
    session: Session = Depends(get_session),
    _: None = Depends(_auth),
):
    asset = session.get(GenericAsset, asset_id)
    if not asset or asset.user_id != _USER_ID:
        raise HTTPException(404, f"Asset {asset_id} not found")
    return {
        "id": asset.id,
        "asset_class": asset.asset_class,
        "name": asset.name,
        "identifier": asset.identifier,
        "identifier_type": asset.identifier_type,
        "quantity": asset.quantity,
        "condition": asset.condition,
        "purchase_price": asset.purchase_price,
        "currency": asset.currency,
        "acquired_from": asset.acquired_from,
        "acquired_at": asset.acquired_at,
        "sale_price": asset.sale_price,
        "sale_date": asset.sale_date,
        "sale_platform": asset.sale_platform,
        "asset_metadata": json.loads(asset.asset_metadata) if asset.asset_metadata else None,
        "notes": asset.notes,
        "created_at": asset.created_at,
    }


@router.post("/assets", status_code=201)
def add_asset(
    payload: GenericAssetAddRequest,
    session: Session = Depends(get_session),
    _: None = Depends(_auth),
):
    """
    Add a generic asset. Merges by (user_id, identifier, identifier_type)
    when an identifier is present; otherwise always creates a new row.
    """
    existing = None
    if payload.identifier and payload.identifier_type:
        existing = session.exec(
            select(GenericAsset).where(
                GenericAsset.user_id == _USER_ID,
                GenericAsset.identifier == payload.identifier,
                GenericAsset.identifier_type == payload.identifier_type,
            )
        ).first()

    meta_str = json.dumps(payload.asset_metadata) if payload.asset_metadata else None

    if existing:
        existing.quantity += max(1, payload.quantity)
        if payload.notes:
            existing.notes = payload.notes
        if meta_str and not existing.asset_metadata:
            existing.asset_metadata = meta_str
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return {"id": existing.id, "name": existing.name, "merged": True, "quantity": existing.quantity}

    new_asset = GenericAsset(
        user_id=_USER_ID,
        asset_class=payload.asset_class,
        name=payload.name,
        identifier=payload.identifier,
        identifier_type=payload.identifier_type,
        quantity=max(1, payload.quantity),
        condition=payload.condition,
        purchase_price=payload.purchase_price,
        currency=payload.currency,
        acquired_from=payload.acquired_from,
        acquired_at=datetime.utcnow() if payload.acquired_from else None,
        asset_metadata=meta_str,
        notes=payload.notes,
    )
    session.add(new_asset)
    session.commit()
    session.refresh(new_asset)
    return {"id": new_asset.id, "name": new_asset.name, "merged": False, "quantity": new_asset.quantity}


@router.delete("/assets/{asset_id}", status_code=204)
def delete_asset(
    asset_id: int,
    session: Session = Depends(get_session),
    _: None = Depends(_auth),
):
    asset = session.get(GenericAsset, asset_id)
    if not asset or asset.user_id != _USER_ID:
        raise HTTPException(404, f"Asset {asset_id} not found")
    session.delete(asset)
    session.commit()
