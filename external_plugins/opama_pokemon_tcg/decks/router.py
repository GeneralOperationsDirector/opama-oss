"""
Decks API router — Pokémon TCG deck building (mounted at /decks).

CRUD for a user's decks and the cards within them. Every endpoint requires auth
and is scoped to the active organization (pool tenancy) via `_assert_deck_access()`;
card adds are idempotent (merge-on-duplicate by deck + card). Card *suggestions*
live in the separate `opama_ai` router, not here.
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from services.shared.database import get_session
from services.shared.models import User
from opama_pokemon_tcg.decks.models import Deck, DeckCard
from opama_pokemon_tcg.decks.validation import validate_deck
from opama_pokemon_tcg.catalog.models import Card
from services.auth.middleware import get_current_user
from services.auth.org_context import OrgContext, get_current_org

router = APIRouter()


def _assert_deck_access(deck: Deck, ctx: OrgContext) -> None:
    if deck.org_id != ctx.org_id:
        raise HTTPException(403, "Cannot access another organization's deck")


# ---------------------------------------------------------------------------
# Decks
# ---------------------------------------------------------------------------


@router.get("")
def list_decks(
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(get_current_org),
) -> List[Deck]:
    """List decks for the active organization, newest-first."""
    q = select(Deck).where(Deck.org_id == ctx.org_id)
    return session.exec(q.order_by(Deck.id.desc())).all()


@router.post("")
def create_deck(
    payload: Dict[str, Any],
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    ctx: OrgContext = Depends(get_current_org),
) -> Deck:
    """
    Create a new deck in the active organization.

    Payload:
      - name (str, required)
      - format (str, optional; e.g., "Standard")
    """
    name = (payload.get("name") or "").strip()
    fmt = payload.get("format")

    if not name:
        raise HTTPException(422, "name is required")

    deck = Deck(
        org_id=ctx.org_id,            # owning organization (tenancy/RLS scope)
        user_id=current_user.id,      # creating/acting user (audit)
        name=name,
        format=fmt,
    )
    session.add(deck)
    session.commit()
    session.refresh(deck)
    return deck


@router.get("/{deck_id}")
def get_deck(
    deck_id: int,
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(get_current_org),
):
    """Get a deck and its cards (hydrated with minimal card info)."""
    deck = session.get(Deck, deck_id)
    if not deck:
        raise HTTPException(404, "Deck not found")
    _assert_deck_access(deck, ctx)

    dcs: List[DeckCard] = session.exec(
        select(DeckCard).where(DeckCard.deck_id == deck_id)
    ).all()

    card_ids = list({dc.card_id for dc in dcs})
    cards = {
        c.id: c for c in session.exec(select(Card).where(Card.id.in_(card_ids))).all()
    }

    hydrated = []
    for dc in dcs:
        c = cards.get(dc.card_id)
        hydrated.append(
            {
                "id": dc.id,
                "deck_id": dc.deck_id,
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
                        "image_small": c.image_small,
                    }
                    if c
                    else None
                ),
            }
        )
    return {"deck": deck, "cards": hydrated}


@router.get("/{deck_id}/validate")
def validate_deck_endpoint(
    deck_id: int,
    format: Optional[str] = Query(None, description="standard | expanded | unlimited; defaults to the deck's format"),
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(get_current_org),
):
    """Validate a deck's construction + format legality.

    Returns `{format, legal, total, counts, issues[]}`. Checks the 60-card count,
    the ≤4-copy rule (basic Energy exempt), ≥1 Basic Pokémon, ACE SPEC/Radiant
    limits, and per-card legality for the chosen format (defaults to the deck's
    own `format`, else Standard).
    """
    deck = session.get(Deck, deck_id)
    if not deck:
        raise HTTPException(404, "Deck not found")
    _assert_deck_access(deck, ctx)

    dcs: List[DeckCard] = session.exec(
        select(DeckCard).where(DeckCard.deck_id == deck_id)
    ).all()
    card_ids = list({dc.card_id for dc in dcs})
    cards = {
        c.id: c for c in session.exec(select(Card).where(Card.id.in_(card_ids))).all()
    }

    entries = [(cards[dc.card_id], dc.quantity) for dc in dcs if dc.card_id in cards]
    result = validate_deck(entries, format or deck.format or "standard")

    # Surface any deck cards whose catalog entry is missing (can't be validated).
    missing = sorted({dc.card_id for dc in dcs if dc.card_id not in cards})
    payload = result.to_dict()
    if missing:
        payload["issues"].append({
            "code": "unknown_card", "severity": "warning",
            "message": f"{len(missing)} card(s) not in the catalog and not validated.",
            "card_name": None,
        })
        payload["legal"] = payload["legal"] and True  # missing cards are a warning, not an error
    return payload


@router.patch("/{deck_id}")
def rename_deck(
    deck_id: int,
    payload: Dict[str, Any],
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(get_current_org),
):
    """Rename a deck and/or update its format."""
    deck = session.get(Deck, deck_id)
    if not deck:
        raise HTTPException(404, "Deck not found")
    _assert_deck_access(deck, ctx)

    if "name" in payload and payload["name"]:
        deck.name = str(payload["name"])
    if "format" in payload:
        deck.format = payload["format"]

    session.add(deck)
    session.commit()
    session.refresh(deck)
    return deck


@router.delete("/{deck_id}")
def delete_deck(
    deck_id: int,
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(get_current_org),
):
    """Delete a deck and its DeckCards."""
    deck = session.get(Deck, deck_id)
    if not deck:
        raise HTTPException(404, "Deck not found")
    _assert_deck_access(deck, ctx)

    for dc in session.exec(select(DeckCard).where(DeckCard.deck_id == deck_id)).all():
        session.delete(dc)

    session.delete(deck)
    session.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Deck cards
# ---------------------------------------------------------------------------


@router.post("/{deck_id}/cards")
def add_deck_card(
    deck_id: int,
    payload: Dict[str, Any],
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(get_current_org),
):
    """Add a card to a deck (idempotent: existing card increments quantity)."""
    deck = session.get(Deck, deck_id)
    if not deck:
        raise HTTPException(404, "Deck not found")
    _assert_deck_access(deck, ctx)

    card_id = str(payload.get("card_id") or "").strip()
    qty = int(payload.get("quantity") or 1)
    role = payload.get("role")

    if not card_id:
        raise HTTPException(400, "card_id is required")
    if not session.get(Card, card_id):
        raise HTTPException(404, f"Card {card_id} not found")

    existing = session.exec(
        select(DeckCard).where(
            (DeckCard.deck_id == deck_id) & (DeckCard.card_id == card_id)
        )
    ).first()

    if existing:
        existing.quantity += max(1, qty)
        if role is not None:
            existing.role = role
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return {
            "id": existing.id,
            "deck_id": existing.deck_id,
            "card_id": existing.card_id,
            "quantity": existing.quantity,
            "role": existing.role,
        }

    dc = DeckCard(deck_id=deck_id, card_id=card_id, quantity=max(1, qty), role=role)
    session.add(dc)
    session.commit()
    session.refresh(dc)
    return {
        "id": dc.id,
        "deck_id": dc.deck_id,
        "card_id": dc.card_id,
        "quantity": dc.quantity,
        "role": dc.role,
    }


@router.patch("/{deck_id}/cards/{deck_card_id}")
def patch_deck_card(
    deck_id: int,
    deck_card_id: int,
    payload: Dict[str, Any],
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(get_current_org),
):
    """Update quantity or role of a DeckCard. Deletes row if quantity reaches 0."""
    dc = session.get(DeckCard, deck_card_id)
    if not dc or dc.deck_id != deck_id:
        raise HTTPException(404, "Deck card not found")

    deck = session.get(Deck, deck_id)
    _assert_deck_access(deck, ctx)

    qd = int(payload.get("quantity_delta") or 0)
    if qd != 0:
        dc.quantity += qd
        if dc.quantity <= 0:
            session.delete(dc)
            session.commit()
            return {"deleted": True}

    if "role" in payload:
        dc.role = payload["role"]

    session.add(dc)
    session.commit()
    session.refresh(dc)
    return {"deleted": False, "card": dc}


@router.delete("/{deck_id}/cards/{deck_card_id}")
def delete_deck_card(
    deck_id: int,
    deck_card_id: int,
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(get_current_org),
):
    """Remove a single DeckCard row from the deck."""
    dc = session.get(DeckCard, deck_card_id)
    if not dc or dc.deck_id != deck_id:
        raise HTTPException(404, "Deck card not found")

    deck = session.get(Deck, deck_id)
    _assert_deck_access(deck, ctx)

    session.delete(dc)
    session.commit()
    return {"ok": True}
