"""
Suggestions & Deck Chat API
---------------------------
Exposes:
1) Heuristic recommendations (GET /suggest/{deck_id})
2) LLM-based recommendations (POST /suggest/ai)
3) Deck-focused chat with grounded context (POST /suggest/chat)
4) Build-a-deck-from-inventory (POST /suggest/build_from_inventory)

Design goals:
- Stable, explicit JSON schemas for frontends.
- Predictable ownership filters (owned_only/acquire_only) with clear notes.
- Defensive OpenAI client support (new vs legacy SDKs).

Extras:
- Optional Redis caching for heuristic + AI responses.
- Pagination on owned_only heuristic view.
"""

from __future__ import annotations
from typing import List, Optional, Dict, Any, Union, Literal, DefaultDict

from fastapi import APIRouter, Depends, HTTPException, Body, Query, Request
from pydantic import BaseModel, Field
from sqlmodel import Session, select
from slowapi import Limiter
from slowapi.util import get_remote_address

from services.shared.database import get_session
from opama_pokemon_tcg.decks.models import Deck, DeckCard
from opama_pokemon_tcg.catalog.models import Card, CardFeatures, Set
from opama_pokemon_tcg.inventory.models import InventoryItem
from .rag import cache  # Redis-backed JSON cache (opt-in)
from .providers import (
    LLMMessage,
    LLMProviderError,
    get_provider,
    parse_json_loose,
)
import json

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

router = APIRouter()


# ---------- Schemas ----------
class Rec(BaseModel):
    """
    Normalized recommendation row.

    Rationale: `reason` explains *why* the card is recommended.
    `confidence` is a heuristic/LLM score; optional and not guaranteed comparable
    across endpoints (document per-endpoint scale if needed).
    """

    # Core identity
    card_id: str
    name: str

    # Printing / catalog metadata (nullable for LLM-only suggestions)
    set: Optional[str] = None  # legacy alias for `set_id`
    set_id: Optional[str] = None
    set_name: Optional[str] = None
    series: Optional[str] = None
    number: Optional[str] = None
    rarity: Optional[str] = None
    types: Optional[str] = None
    subtypes: Optional[str] = None

    # Ownership / deck context
    owned_quantity: Optional[int] = None
    in_deck: Optional[bool] = None

    # Rationale
    reason: str
    confidence: Optional[float] = None  # 0..1 recommended (not enforced)


class HeuristicResponse(BaseModel):
    """Wire shape for the heuristic endpoint (and owned_only listing)."""

    recommendations: List[Rec] = Field(default_factory=list)
    note: Optional[str] = None  # messaging when filters ignored/adjusted


class AiSuggestIn(BaseModel):
    """
    Input for AI suggestions.

    `owned_only` / `acquire_only` require a resolvable user_id; if both are set,
    we default to `acquire_only`.
    """

    deck_id: int
    user_id: Optional[Union[int, str]] = None
    n: int = 10
    model: Optional[str] = None
    temperature: float = 0.3
    prompt: Optional[str] = None  # optional extra instruction for advanced clients
    owned_only: bool = False
    acquire_only: bool = False
    cache_seconds: int = Field(0, ge=0, description="If >0, cache for N seconds")
    # TODO(rate): optional per-user rate limiting / cache key scoping by user


class AiSuggestOut(BaseModel):
    """Strict JSON output for AI suggestions."""

    recommendations: List[Rec] = Field(default_factory=list)
    note: Optional[str] = None


class ChatMessage(BaseModel):
    """OpenAI-format chat message."""

    role: Literal["system", "user", "assistant"]
    content: str


class ChatIn(BaseModel):
    """Chat grounded by a deck (and optionally ownership)."""

    deck_id: int
    user_id: Optional[Union[int, str]] = None
    messages: List[ChatMessage]  # include entire chat history so far (no context)
    model: Optional[str] = None
    temperature: float = 0.5


class ChatOut(BaseModel):
    """Chat response + model + OpenAI-style usage (if available)."""

    reply: str
    model: str
    usage: Optional[Dict[str, Any]] = None


# ---------- tiny utils ----------
def _clamp_int(v: int, lo: int, hi: int) -> int:
    """Clamp an int; if non-numeric, returns `lo`."""
    try:
        v = int(v)
    except Exception:
        return lo
    return max(lo, min(hi, v))


def parse_optional_int(v: Optional[Union[int, str]]) -> Optional[int]:
    """
    Normalize user-supplied numeric-ish IDs:
    'undefined'/'null'/''/None -> None, numbers/num-strings -> int, else None.
    """
    if v is None:
        return None
    if isinstance(v, int):
        return v
    s = str(v).strip().lower()
    if s in ("", "undefined", "null", "none"):
        return None
    try:
        return int(s)
    except Exception:
        return None


# --- Compact deck/inventory context for grounding the chat ---
def _deck_chat_context(
    session: Session, deck_id: int, uid: Optional[int]
) -> Dict[str, Any]:
    """
    Compose compact JSON context for chat grounding:
      - deck summary
      - deck list (qty/card_id/name/set/number/types/stage/role)
      - (optional) owned_summary: {card_id: total_owned}
    """
    data = _load_deck_with_cards(session, deck_id)
    deck = data["deck"]
    dcards = data["cards"]

    deck_lines = []
    for dc in dcards:
        c = dc["card"]
        deck_lines.append(
            {
                "qty": dc["quantity"],
                "card_id": dc["card_id"],
                "name": (c or {}).get("name"),
                "set": (c or {}).get("set_id"),
                "number": (c or {}).get("number"),
                "types": (c or {}).get("types"),
                "stage": (c or {}).get("stage"),
                "role": dc.get("role"),
            }
        )

    ctx: Dict[str, Any] = {
        "deck": {"id": deck.id, "name": deck.name, "format": deck.format},
        "cards": deck_lines,
    }

    if uid is not None:
        # Optimized: Use GROUP BY instead of loading all inventory items
        from sqlalchemy import func
        results = session.exec(
            select(InventoryItem.card_id, func.sum(InventoryItem.quantity))
            .where(InventoryItem.user_id == uid)
            .group_by(InventoryItem.card_id)
        ).all()
        owned_summary: Dict[str, int] = {
            card_id: int(qty or 0) for card_id, qty in results
        }
        ctx["owned_summary"] = owned_summary

    return ctx


# ---------- Chat POST ----------
@router.post("/chat", response_model=ChatOut)
@limiter.limit("5/minute")
def chat_about_deck(
    request: Request,
    payload: ChatIn = Body(...),
    session: Session = Depends(get_session),
):
    """
    LLM chat about a specific deck, grounded by compact deck/owned context.

    Strategy:
      - Two system messages: primer + JSON-encoded context
      - Then user-provided messages (full history) for continuity

    TODO(prompting): Consider adding an `instruction_version` flag so you
                     can evolve prompts without breaking pinned clients.
    """
    uid = parse_optional_int(payload.user_id)
    try:
        provider = get_provider()
    except LLMProviderError as e:
        raise HTTPException(status_code=400, detail=str(e))

    model = payload.model or provider.default_model

    # System primer + deck context (as system message)
    system = (
        "You are a Pokémon TCG deck-building assistant. Be concrete and practical. "
        "Use the provided deck context; when recommending cards, include exact set codes when you know them."
    )
    ctx = _deck_chat_context(session, payload.deck_id, uid)

    messages = [
        LLMMessage(role="system", content=system),
        LLMMessage(role="system", content=json.dumps({"context": ctx})),
        *[LLMMessage(role=m.role, content=m.content) for m in payload.messages],
    ]

    try:
        result = provider.chat(messages, model=model, temperature=payload.temperature)
        return ChatOut(reply=result.content, model=result.model, usage=result.usage)
    except LLMProviderError as e:
        # Upstream failure → clear 502 to inform clients this is retriable.
        raise HTTPException(status_code=502, detail=str(e))


# ---------- Helpers ----------
def _load_deck_with_cards(session: Session, deck_id: int) -> Dict[str, Any]:
    """
    Hydrate a deck with DeckCards and a minimal snapshot of Card fields
    used across suggest/chat outputs.

    NOTE: If you expand the frontend needs, extend the picked fields here.
    """
    deck = session.get(Deck, deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail=f"Deck {deck_id} not found")

    dcs: List[DeckCard] = session.exec(
        select(DeckCard).where(DeckCard.deck_id == deck_id)
    ).all()
    card_ids = [dc.card_id for dc in dcs]
    cards = {
        c.id: c for c in session.exec(select(Card).where(Card.id.in_(card_ids))).all()
    }

    items = []
    for dc in dcs:
        c = cards.get(dc.card_id)
        items.append(
            {
                "id": dc.id,
                "card_id": dc.card_id,
                "quantity": dc.quantity,
                "role": dc.role,
                "card": (
                    {
                        "id": c.id,
                        "name": c.name,
                        "set_id": c.set_id,
                        "number": c.number,
                        "rarity": c.rarity,
                        "types": c.types,
                        "subtypes": c.subtypes,
                        "stage": c.stage,
                        "supertype": c.supertype,
                        "hp": c.hp,
                        "ability_name": c.ability_name,
                        "attack1_name": c.attack1_name,
                        "attack1_damage": c.attack1_damage,
                        "attack2_name": c.attack2_name,
                        "attack2_damage": c.attack2_damage,
                    }
                    if c
                    else None
                ),
            }
        )
    return {"deck": deck, "cards": items}


def _owned_card_ids(session: Session, user_id: Optional[int]) -> set[str]:
    """Return {card_id} with quantity > 0 for user (empty set when user_id missing)."""
    if not user_id:
        return set()
    inv: List[InventoryItem] = session.exec(
        select(InventoryItem).where(InventoryItem.user_id == user_id)
    ).all()
    return {i.card_id for i in inv if i.quantity and i.quantity > 0}


def _owned_map(session: Session, user_id: int) -> Dict[str, int]:
    """Return card_id -> total owned quantity for the user."""
    inv: List[InventoryItem] = session.exec(
        select(InventoryItem).where(InventoryItem.user_id == user_id)
    ).all()
    out: Dict[str, int] = {}
    for it in inv:
        out[it.card_id] = out.get(it.card_id, 0) + (it.quantity or 0)
    return out


def _catalog_cards(session: Session) -> Dict[str, Card]:
    """
    Return all cards keyed by card_id.

    WARNING: If catalog grows very large, avoid this full load; instead query
    only the subset of cards you need (e.g., by feature presence).
    """
    cards = session.exec(select(Card)).all()
    return {c.id: c for c in cards}


def _sets_map(session: Session) -> Dict[str, Set]:
    """Return all sets keyed by set.id (memoize/cache if used frequently)."""
    sets = session.exec(select(Set)).all()
    return {s.id: s for s in sets}


def _add_if_not_present(dst: List[Rec], r: Rec, seen: set[str]):
    """Append a Rec only if its card_id hasn't been emitted."""
    key = f"{r.card_id}"
    if key not in seen:
        dst.append(r)
        seen.add(key)


# ---------- Heuristic GET ----------
@router.get("/{deck_id}", response_model=HeuristicResponse)
def suggest_for_deck(
    deck_id: int,
    session: Session = Depends(get_session),
    limit: int = Query(10, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user_id: Optional[str] = Query(None),  # accept string; coerce safely below
    owned_only: bool = Query(False),
    acquire_only: bool = Query(False),
    cache_seconds: int = Query(0, ge=0, description="If >0, cache for N seconds"),
):
    """
    Heuristic recommendations for a deck.

    Special path:
      - owned_only=true + user_id → returns per-printing *owned* list
        (with owned_quantity + in_deck flags) and supports pagination.

    NOTE:
      - Limit/offset clamped defensively. For very large datasets, consider
        switching to cursor-based pagination.
    """
    # Defensive clamps
    limit = _clamp_int(limit, 1, 200)
    offset = _clamp_int(offset, 0, 10_000)

    uid = parse_optional_int(user_id)
    note: Optional[str] = None

    # Ownership filters require a valid user
    if (owned_only or acquire_only) and uid is None:
        note = "Ownership filter requested but user_id missing/invalid; ignoring."
        owned_only = False
        acquire_only = False

    # Cache lookup (only if requested)
    cache_key = None
    if cache_seconds > 0:
        cache_key = {
            "route": "suggest_heuristic",
            "deck_id": deck_id,
            "uid": uid,
            "owned_only": owned_only,
            "acquire_only": acquire_only,
            "limit": limit,
            "offset": offset,
        }
        hit = cache.get(cache_key)
        if hit is not None:
            return HeuristicResponse(**hit)  # return cached wire shape

    data = _load_deck_with_cards(session, deck_id)
    dcards = data["cards"]
    deck_card_ids = {dc["card_id"] for dc in dcards}

    # Fast lookups (consider memoizing in a request cache if reused often)
    cards_by_id = _catalog_cards(session)
    sets_by_id = _sets_map(session)

    # ---- OWNED-ONLY: exact per-printing output ----
    if owned_only and uid is not None:
        q = (
            select(InventoryItem, Card, Set)
            .where(InventoryItem.user_id == uid)
            .join(Card, Card.id == InventoryItem.card_id)
            .join(Set, Set.id == Card.set_id)
        )
        rows = session.exec(q).all()

        recs: List[Rec] = []
        for inv, card, s in rows:
            recs.append(
                Rec(
                    card_id=card.id,
                    name=card.name,
                    set_id=card.set_id,
                    set=card.set_id,  # legacy alias
                    set_name=s.name,
                    series=s.series,
                    number=card.number,
                    rarity=card.rarity,
                    types=card.types,
                    subtypes=card.subtypes,
                    owned_quantity=inv.quantity or 0,
                    in_deck=(card.id in deck_card_ids),
                    reason="Owned printing",
                    confidence=None,
                )
            )

        # Sort primarily by owned quantity, then by name/set/number for stability
        recs.sort(
            key=lambda r: (
                -(r.owned_quantity or 0),
                r.name or "",
                r.set_id or "",
                r.number or "",
            )
        )

        # Pagination slice
        if offset:
            recs = recs[offset:]
        if limit:
            recs = recs[:limit]

        resp = HeuristicResponse(recommendations=recs, note=note or "owned_only")

        if cache_seconds > 0 and cache_key is not None:
            cache.set(cache_key, resp.model_dump(), ttl=cache_seconds)

        return resp

    # ---- GENERAL / ACQUIRE heuristic: score by features & synergy ----
    owned_ids = _owned_card_ids(session, uid) if (owned_only or acquire_only) else set()

    # Optimized: Load only CardFeatures for cards in our catalog, not all 50k+ records
    catalog_card_ids = list(cards_by_id.keys())
    feat_map = {
        f.card_id: f
        for f in session.exec(
            select(CardFeatures).where(CardFeatures.card_id.in_(catalog_card_ids))
        ).all()
    }

    # Build a candidate pool of "useful" cards based on features or evolutions
    pool: List[Card] = []
    for c in cards_by_id.values():
        f = feat_map.get(c.id)
        useful = False
        if f:
            useful = any(
                [
                    f.provides_draw,
                    f.provides_search,
                    f.switching,
                    f.gust_effect,
                    f.stadium,
                    f.healing,
                    f.disruption,
                    f.recovery,
                ]
            )
        # Allow evolution helpers if deck already includes the basic
        if not useful and c.stage in ("Stage 1", "Stage 2") and c.evolves_from:
            basic_in_deck = any(
                (dc["card"] and (dc["card"]["name"] == c.evolves_from)) for dc in dcards
            )
            if basic_in_deck:
                useful = True
        if useful:
            pool.append(c)

    # Optimized: Pre-compute deck types once instead of recalculating for every card
    deck_types_set: set[str] = set()
    for dc in dcards:
        t = (dc["card"] or {}).get("types") or ""
        deck_types_set.update(x.strip() for x in t.split(",") if x.strip())

    def score(card: Card) -> float:
        """
        Heuristic score (0..~3):
          +1.0 draw/search
          +0.5 switching/gust, +0.25 stadium/disruption/recovery/healing
          +0.4 same-type synergy
          -0.5 if already in deck
        """
        s = 0.0
        f = feat_map.get(card.id)
        if f:
            s += 1.0 if (f.provides_draw or f.provides_search) else 0.0
            s += 0.5 if f.switching else 0.0
            s += 0.5 if f.gust_effect else 0.0
            s += 0.25 if f.stadium else 0.0
            s += 0.25 if (f.disruption or f.recovery or f.healing) else 0.0

        # Same-type bump based on deck composition (using pre-computed set for O(1) lookup)
        if card.types:
            c_types = [x.strip() for x in card.types.split(",") if x.strip()]
            if any(t in deck_types_set for t in c_types):
                s += 0.4

        # Down-rank if already in deck
        if card.id in deck_card_ids:
            s -= 0.5
        return s

    ranked = sorted(pool, key=score, reverse=True)

    def passes_ownership(c: Card) -> bool:
        if not owned_ids:
            return True
        if owned_only:
            return c.id in owned_ids
        if acquire_only:
            return c.id not in owned_ids
        return True

    # Build up to offset+limit then slice (saves work)
    target = offset + limit
    out: List[Rec] = []
    seen: set[str] = set()

    for c in ranked:
        if not passes_ownership(c):
            continue
        s = sets_by_id.get(c.set_id)
        f = feat_map.get(c.id)
        reason_bits = []
        if f:
            if f.provides_draw:
                reason_bits.append("draw")
            if f.provides_search:
                reason_bits.append("search")
            if f.switching:
                reason_bits.append("switching")
            if f.gust_effect:
                reason_bits.append("gust")
            if f.stadium:
                reason_bits.append("stadium")
            if f.disruption:
                reason_bits.append("disruption")
            if f.recovery:
                reason_bits.append("recovery")
            if f.healing:
                reason_bits.append("healing")
        if c.stage in ("Stage 1", "Stage 2") and c.evolves_from:
            reason_bits.append(f"evolves from {c.evolves_from}")
        reason = ", ".join(reason_bits) or "useful tech"

        rec = Rec(
            card_id=c.id,
            name=c.name,
            set_id=c.set_id,
            set=c.set_id,  # legacy alias
            set_name=(s.name if s else None),
            series=(s.series if s else None),
            number=c.number,
            rarity=c.rarity,
            types=c.types,
            subtypes=c.subtypes,
            owned_quantity=None,
            in_deck=(c.id in deck_card_ids),
            reason=reason,
            confidence=round(score(c), 3),
        )
        _add_if_not_present(out, rec, seen)
        if len(out) >= target:
            break

    # Apply offset/limit
    out = out[offset : offset + limit] if offset else out[:limit]

    resp = HeuristicResponse(recommendations=out, note=note)
    if cache_seconds > 0 and cache_key is not None:
        cache.set(cache_key, resp.model_dump(), ttl=cache_seconds)
    return resp


# ---------- AI POST ----------
@router.post("/ai", response_model=AiSuggestOut)
@limiter.limit("10/minute")
def ai_suggest(
    request: Request,
    payload: AiSuggestIn = Body(...),
    session: Session = Depends(get_session)
):
    """
    LLM-based suggestions with strict JSON output.

    Rate Limit: 10 requests per minute per IP (AI is expensive).

    Contract:
      - Prompts for `{recommendations: [{card_id, name, set, reason, confidence}]}`.
      - Honors ownership filters when user_id is present (owned_only/acquire_only).
      - Supports opt-in Redis caching via `cache_seconds`.

    NOTE: We still verify card_ids against our catalog before emitting results,
          so frontends get enriched metadata and consistent `Rec` shapes.
    """
    # Clamp n (defensive)
    payload.n = _clamp_int(payload.n, 1, 100)

    uid = parse_optional_int(payload.user_id)
    note: Optional[str] = None
    owned_only = payload.owned_only
    acquire_only = payload.acquire_only

    # Guard: both set → prefer acquire_only (clear external messaging)
    if owned_only and acquire_only:
        acquire_only = True
        owned_only = False
        note = "Both owned_only and acquire_only set; using acquire_only."

    if (owned_only or acquire_only) and uid is None:
        owned_only = False
        acquire_only = False
        note = "Ownership filter requested but user_id missing/invalid; ignoring."

    # Cache lookup (only if requested)
    cache_key = None
    if payload.cache_seconds > 0:
        cache_key = {
            "route": "suggest_ai",
            "deck_id": payload.deck_id,
            "uid": uid,
            "n": payload.n,
            "model": payload.model or "auto",
            "temperature": round(float(payload.temperature), 3),
            "owned_only": owned_only,
            "acquire_only": acquire_only,
            "prompt_present": bool(payload.prompt),
        }
        hit = cache.get(cache_key)
        if hit is not None:
            return AiSuggestOut(**hit)

    data = _load_deck_with_cards(session, payload.deck_id)
    dcards = data["cards"]

    owned_ids = _owned_card_ids(session, uid)
    catalog = _catalog_cards(session)
    sets_by_id = _sets_map(session)

    # Compact deck context for the model (kept lean for token economy)
    deck_lines = []
    for dc in dcards:
        c = dc["card"]
        deck_lines.append(
            {
                "qty": dc["quantity"],
                "card_id": dc["card_id"],
                "name": (c or {}).get("name"),
                "set": (c or {}).get("set_id"),
                "number": (c or {}).get("number"),
                "types": (c or {}).get("types"),
                "stage": (c or {}).get("stage"),
                "role": dc.get("role"),
            }
        )

    # System prompt constrains output to strict JSON (helps with legacy SDK)
    system = (
        "You are a Pokémon TCG deck building assistant. "
        "Recommend specific cards (by exact set id code like 'sv9-12') that improve the given deck. "
        "Prefer synergy, search/draw, switching, gust, stadiums, and evolution lines that match what's present. "
        "Respond as strict JSON with key 'recommendations' as a list of objects: "
        "{card_id, name, set, reason, confidence}."
    )
    user_parts: List[Dict[str, Any]] = [
        {
            "deck": data["deck"].name,
            "deck_id": data["deck"].id,
            "format": data["deck"].format,
        },
        {"deck_cards": deck_lines},
        {"owned_only": owned_only, "acquire_only": acquire_only},
        {"n": payload.n},
    ]
    # Include ownership summary when available
    if uid is not None:
        inv: List[InventoryItem] = session.exec(
            select(InventoryItem).where(InventoryItem.user_id == uid)
        ).all()
        owned_summary: Dict[str, int] = {}
        for it in inv:
            owned_summary[it.card_id] = owned_summary.get(it.card_id, 0) + (
                it.quantity or 0
            )
        user_parts.append({"owned_summary": owned_summary})

    # LLM call
    try:
        provider = get_provider()
    except LLMProviderError as e:
        raise HTTPException(status_code=400, detail=str(e))

    model = payload.model or provider.default_model

    raw_json: Optional[Union[Dict[str, Any], List[Any]]] = None
    try:
        result = provider.chat_json(
            [
                LLMMessage(role="system", content=system),
                LLMMessage(role="user", content=json.dumps(user_parts)),
            ],
            model=model,
            temperature=payload.temperature,
        )
        raw_json = parse_json_loose(result.content)
    except HTTPException:
        raise
    except (LLMProviderError, json.JSONDecodeError) as e:
        # Treat upstream transport/parse errors as 500 (not the client's fault)
        # TODO(obs): log payload.n, deck_id (no PII) for triage.
        raise HTTPException(
            status_code=500, detail=f"AI request failed: {type(e).__name__}: {e}"
        )

    # Normalize and validate recommendations against our catalog.
    # Providers without native JSON-object mode (e.g. Ollama) sometimes
    # return a bare array despite the "key 'recommendations'" instruction.
    if isinstance(raw_json, list):
        recs_in = raw_json
    else:
        recs_in = (raw_json or {}).get("recommendations", [])
    out: List[Rec] = []
    seen: set[str] = set()

    def passes(cid: str) -> bool:
        if owned_only and uid is not None:
            return cid in owned_ids
        if acquire_only and uid is not None:
            return cid not in owned_ids
        return True

    for r in recs_in:
        cid = str(r.get("card_id") or "").strip()
        if not cid or not passes(cid):
            continue
        c = catalog.get(cid)
        s = sets_by_id.get(c.set_id) if c else None
        name = r.get("name") or (c.name if c else cid)
        set_id = r.get("set") or (c.set_id if c else None)
        reason = r.get("reason") or "recommended upgrade"
        conf = r.get("confidence")
        try:
            conf = float(conf) if conf is not None else None
        except Exception:
            conf = None

        _add_if_not_present(
            out,
            Rec(
                card_id=cid,
                name=name,
                set=set_id,
                set_id=set_id,
                set_name=(s.name if s else None),
                series=(s.series if s else None),
                number=(c.number if c else None),
                rarity=(c.rarity if c else None),
                types=(c.types if c else None),
                subtypes=(c.subtypes if c else None),
                owned_quantity=None,
                in_deck=None,
                reason=reason,
                confidence=conf,
            ),
            seen,
        )
        if len(out) >= payload.n:
            break

    result = AiSuggestOut(recommendations=out, note=note)
    if payload.cache_seconds > 0 and cache_key is not None:
        cache.set(cache_key, result.model_dump(), ttl=payload.cache_seconds)
    return result


# ---- Build a deck from inventory (from scratch) ------------------------------
from collections import defaultdict, Counter


class BuildFromInvIn(BaseModel):
    """
    Build a simple deck from a user's inventory with light heuristics.

    `primary_types` restricts to target types (e.g., ["Water"] or ["Fire","Lightning"]).
    `deck_size` defaults to 60; minimum 20 to keep logic sane.
    """

    user_id: int
    primary_types: Optional[List[str]] = Field(
        default=None, description="e.g. ['Fire'] or ['Water','Lightning']"
    )
    deck_size: int = Field(default=60, ge=20, le=60)
    # Future: include_ai: bool = False (hybrid heuristic + LLM fill-in)


class DeckLine(BaseModel):
    """One deck line (id, name, qty, role)."""

    card_id: str
    name: str
    qty: int
    role: Optional[str] = (
        None  # 'Basic', 'Stage 1', 'Supporter', 'Stadium', 'Item', 'Energy', etc.
    )


class BuildFromInvOut(BaseModel):
    """Response for build_from_inventory."""

    deck: List[DeckLine]
    summary: Dict[str, Any]
    acquire_suggestions: List[Rec] = Field(default_factory=list)
    notes: Optional[str] = None


def _to_int(s: Optional[str]) -> int:
    """Extract the first integer in a string like '120+' or '–'. Returns 0 if none."""
    if not s:
        return 0
    try:
        import re

        m = re.search(r"\d+", s)
    except Exception:
        m = None
    return int(m.group(0)) if m else 0


def _total_damage(card: Card) -> int:
    """Rough damage proxy: sum numeric parts of up to 3 attacks."""
    return (
        _to_int(card.attack1_damage)
        + _to_int(card.attack2_damage)
        + _to_int(card.attack3_damage)
    )


def _split_types(s: Optional[str]) -> List[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def _role_for_trainer(card: Card) -> str:
    """Rough role classification from subtypes."""
    sub = (card.subtypes or "").lower()
    if "stadium" in sub:
        return "Stadium"
    if "supporter" in sub:
        return "Supporter"
    if "tool" in sub:
        return "Tool"
    return "Item"


def _stage_role(card: Card) -> str:
    st = (card.stage or "").lower()
    if "basic" in st:
        return "Basic"
    if "stage 1" in st:
        return "Stage 1"
    if "stage 2" in st:
        return "Stage 2"
    return "Pokémon"


def _energy_role(card: Card) -> str:
    sub = (card.subtypes or "").lower()
    return "Special Energy" if "special" in sub else "Basic Energy"


@router.post("/build_from_inventory", response_model=BuildFromInvOut)
def build_from_inventory(
    payload: BuildFromInvIn = Body(...), session: Session = Depends(get_session)
):
    """
    Construct a simple starter deck using the user's owned cards.

    Heuristics:
      - Prefer cards matching `primary_types` (if provided).
      - Aim baseline split: ~20 Pokémon / 30 Trainer / 10 Energy (tuned below).
      - Fill to `deck_size` by best-scoring remaining cards.
      - Suggest pre-evolution acquisitions for Stage 1/2/EX lines included.

    TODO(gamesense): Add basic line balance (e.g., 3-2-2) and energy curve
                     heuristics per type; cap Supporters/Stadiums by ranges.
    """
    uid = payload.user_id

    # Load owned items; bail early if empty
    inv_items: List[InventoryItem] = session.exec(
        select(InventoryItem).where(InventoryItem.user_id == uid)
    ).all()
    if not inv_items:
        return BuildFromInvOut(
            deck=[],
            summary={"note": "No inventory for this user."},
            acquire_suggestions=[],
        )

    card_ids = [it.card_id for it in inv_items]
    cards = {
        c.id: c for c in session.exec(select(Card).where(Card.id.in_(card_ids))).all()
    }
    qty_owned = {
        it.card_id: (it.quantity or 0) for it in inv_items if (it.quantity or 0) > 0
    }

    # Feature map for trainer scoring
    feat_map = {f.card_id: f for f in session.exec(select(CardFeatures)).all()}

    # Filter by primary types (ANY overlap)
    primary = [t.lower() for t in (payload.primary_types or [])]

    def matches_primary(c: Card) -> bool:
        if not primary:
            return True
        c_types = [t.lower() for t in _split_types(c.types)]
        return any(t in c_types for t in primary)

    # Partition inventory into Pokémon / Trainers / Energy pools
    pokemon, trainers, energies = [], [], []
    for cid, q in qty_owned.items():
        c = cards.get(cid)
        if not c:
            continue
        if c.supertype == "Pokémon" and matches_primary(c):
            pokemon.append(c)
        elif c.supertype == "Trainer":
            trainers.append(c)
        elif c.supertype == "Energy" and matches_primary(c):
            energies.append(c)

    # Scoring functions (rough but effective)
    def score_poke(c: Card) -> float:
        return (
            (_to_int(c.hp) * 0.6)
            + (_total_damage(c) * 0.4)
            + (2.0 if "ex" in (c.subtypes or "").lower() else 0.0)
        )

    def score_trainer(c: Card) -> float:
        f = feat_map.get(c.id)
        s = 0.0
        if f:
            s += 2.0 if (f.provides_draw or f.provides_search) else 0.0
            s += 1.0 if f.switching else 0.0
            s += 1.0 if f.gust_effect else 0.0
            s += 1.0 if f.stadium else 0.0
            s += 0.5 if (f.disruption or f.recovery or f.healing) else 0.0
        sub = (c.subtypes or "").lower()
        if "supporter" in sub:
            s += 0.5
        if "stadium" in sub:
            s += 0.25
        return s

    def score_energy(c: Card) -> float:
        return 1.0 if "special" in (c.subtypes or "").lower() else 2.0  # prefer Basic

    pokemon.sort(key=score_poke, reverse=True)
    trainers.sort(key=score_trainer, reverse=True)
    energies.sort(key=score_energy, reverse=True)

    # Targets (can be tuned later)
    target_p, target_t = 20, 30
    target_e = max(6, min(16, payload.deck_size - (target_p + target_t)))

    def take_cards(
        candidates: List[Card], target: int, role_fn, max_per_card: int = 4
    ) -> List[DeckLine]:
        """Greedily take up to target qty from candidates subject to ownership and 4-of rule (trainers/Pokémon)."""
        out: List[DeckLine] = []
        remaining = target
        for c in candidates:
            if remaining <= 0:
                break
            owned = qty_owned.get(c.id, 0)
            if owned <= 0:
                continue
            use = min(owned, max_per_card, remaining)
            if use > 0:
                out.append(
                    DeckLine(card_id=c.id, name=c.name, qty=use, role=role_fn(c))
                )
                remaining -= use
        return out

    deck_lines: List[DeckLine] = []
    deck_lines += take_cards(pokemon, target_p, _stage_role, max_per_card=4)
    deck_lines += take_cards(trainers, target_t, _role_for_trainer, max_per_card=4)

    # Energies: 4-of cap doesn't apply to Basic Energy
    def energy_cap(c: Card) -> int:
        return 99 if "special" not in (c.subtypes or "").lower() else 4

    remaining_e = target_e
    for c in energies:
        if remaining_e <= 0:
            break
        owned = qty_owned.get(c.id, 0)
        if owned <= 0:
            continue
        use = min(energy_cap(c), owned, remaining_e)
        if use > 0:
            deck_lines.append(
                DeckLine(card_id=c.id, name=c.name, qty=use, role=_energy_role(c))
            )
            remaining_e -= use

    # Top up to deck_size with best remaining trainers, then Pokémon, then Basic Energy
    def total_qty(lines: List[DeckLine]) -> int:
        return sum(x.qty for x in lines)


    def add_more(from_list: List[Card], role_fn, cap: int = 4):
        nonlocal deck_lines
        have = Counter({x.card_id: x.qty for x in deck_lines})
        while total_qty(deck_lines) < payload.deck_size:
            added_any = False
            for c in from_list:
                if total_qty(deck_lines) >= payload.deck_size:
                    break
                owned = qty_owned.get(c.id, 0)
                already = have.get(c.id, 0)
                room = min(
                    cap - already,
                    owned - already,
                    payload.deck_size - total_qty(deck_lines),
                )
                if room > 0:
                    deck_lines.append(
                        DeckLine(card_id=c.id, name=c.name, qty=room, role=role_fn(c))
                    )
                    have[c.id] = already + room
                    added_any = True
            if not added_any:
                break  # cannot add more due to ownership or caps

    if total_qty(deck_lines) < payload.deck_size:
        add_more(trainers, _role_for_trainer, cap=4)
    if total_qty(deck_lines) < payload.deck_size:
        add_more(pokemon, _stage_role, cap=4)
    if total_qty(deck_lines) < payload.deck_size and energies:
        add_more(
            [c for c in energies if "special" not in (c.subtypes or "").lower()],
            _energy_role,
            cap=99,
        )

    # Summaries for UI/analytics

    used_counts = Counter({x.card_id: x.qty for x in deck_lines})
    by_supertype: DefaultDict[str, int] = defaultdict(int)
    by_type: DefaultDict[str, int] = defaultdict(int)
    for line in deck_lines:
        c = cards.get(line.card_id)
        if not c:
            continue
        by_supertype[c.supertype or "Other"] += line.qty
        for t in _split_types(c.types):
            by_type[t] += line.qty

    # Acquire suggestions: missing pre-evolutions for Stage1/Stage2/EX lines used
    acquire: List[Rec] = []
    seen_missing: set[str] = set()

    name_to_cards: DefaultDict[str, List[Card]] = defaultdict(list)
    for c in cards.values():
        if c.supertype == "Pokémon":
            name_to_cards[c.name].append(c)

    owned_card_objs = [cards[cid] for cid, q in qty_owned.items() if cid in cards]
    owned_by_name: DefaultDict[str, Dict[str, int]] = defaultdict(
        lambda: {"Basic": 0, "Stage 1": 0, "Stage 2": 0, "EX": 0}
    )
    for c in owned_card_objs:
        stage = (c.stage or "").lower()
        qty = qty_owned.get(c.id, 0)
        if "basic" in stage:
            owned_by_name[c.name]["Basic"] += qty
        elif "stage 1" in stage:
            owned_by_name[c.name]["Stage 1"] += qty
        elif "stage 2" in stage:
            owned_by_name[c.name]["Stage 2"] += qty
        if "ex" in (c.subtypes or "").lower():
            owned_by_name[c.name]["EX"] += qty

    for line in deck_lines:
        c = cards.get(line.card_id)
        if not c or c.supertype != "Pokémon":
            continue
        st = (c.stage or "").lower()
        if "stage 1" in st or "stage 2" in st or "ex" in (c.subtypes or "").lower():
            needed_from = []
            if "stage 1" in st and c.evolves_from:
                needed_from.append(("Basic", c.evolves_from))
            if "stage 2" in st and c.evolves_from:
                needed_from.append(("Stage 1", c.evolves_from))
            if "ex" in (c.subtypes or "").lower() and c.evolves_from:
                needed_from.append(("Basic", c.evolves_from))

            for role_need, name_need in needed_from:
                have_qty = owned_by_name.get(name_need, {}).get(role_need, 0)
                if have_qty <= 0:
                    candidates = session.exec(
                        select(Card).where(Card.name == name_need)
                    ).all()
                    if not candidates:
                        continue
                    cand = candidates[0]
                    if cand.id in seen_missing:
                        continue
                    acquire.append(
                        Rec(
                            card_id=cand.id,
                            name=cand.name,
                            set=cand.set_id,
                            reason=f"Needed pre-evolution ({role_need}) for {c.name}",
                            confidence=0.75,
                        )
                    )
                    seen_missing.add(cand.id)

    summary = {
        "counts": {
            "total": sum(used_counts.values()),
            "by_supertype": dict(by_supertype),
            "by_type": dict(by_type),
        },
        "primary_types": payload.primary_types or [],
        "used_unique": len(used_counts),
        "owned_used": dict(used_counts),
        "owned_leftover": {
            cid: max(0, qty_owned[cid] - used_counts.get(cid, 0)) for cid in qty_owned
        },
    }

    notes = None
    if not pokemon:
        notes = "No Pokémon matching selected types were found in inventory."
    elif sum(x.qty for x in deck_lines) < payload.deck_size:
        notes = "Could not reach full deck size with owned cards; topped up as much as possible."

    # TODO(persist): Offer an option to save this deck as a new Deck row.
    return BuildFromInvOut(
        deck=deck_lines, summary=summary, acquire_suggestions=acquire, notes=notes
    )
