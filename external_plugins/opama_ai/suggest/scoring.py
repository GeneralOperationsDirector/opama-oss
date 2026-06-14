# app/services/suggest.py
"""
Heuristic suggestion service.

Provides lightweight deck improvement suggestions without invoking an LLM.
Currently looks at:
- Average retreat cost → suggests switching cards if high.
- Supporter count      → suggests adding more Supporters if low.
- Stadium presence     → suggests adding stadiums if missing.

Notes:
- Uses simple text heuristics on Card.rules_text and Card.name.
- Intended as a fast fallback or complement to AI-driven suggestions.
"""

from typing import List, Dict
from sqlmodel import Session, select
from sqlalchemy import and_
from ..models import Card, DeckCard


def _to_int_or_zero(v):
    """
    Convert a value to int if possible, else return 0.

    Handles:
        - None → 0
        - Numeric strings → int
        - Non-numeric strings → 0
        - Exceptions → 0
    """
    try:
        if v is None:
            return 0
        s = str(v).strip()
        return int(s) if s.isdigit() else 0
    except Exception:  # TODO: Narrow to ValueError/TypeError for clarity
        return 0


def suggest_improvements(session: Session, deck_id: int, limit: int = 10) -> List[Dict]:
    """
    Suggest cards to improve a given deck using lightweight heuristics.

    Args:
        session: SQLModel session for DB access.
        deck_id: Deck ID to analyze.
        limit:   Max number of suggestions to return.

    Returns:
        List of suggestion dicts:
          {"reason": str, "card": Card}
    """

    # Fetch all DeckCard rows for the deck
    deck_cards = session.exec(select(DeckCard).where(DeckCard.deck_id == deck_id)).all()
    if not deck_cards:
        return []

    # Fetch the Card objects for those deck entries
    card_ids = [dc.card_id for dc in deck_cards]
    cards = session.exec(select(Card).where(Card.id.in_(card_ids))).all()

    # Basic metrics ------------------------------------------------------------
    avg_retreat = sum(_to_int_or_zero(c.retreat_cost) for c in cards) / max(
        1, len(cards)
    )
    rules = lambda c: (c.rules_text or "").lower()

    supporter_count = sum(1 for c in cards if "supporter" in rules(c))
    has_stadium = any("stadium" in rules(c) for c in cards)

    suggestions: List[Dict] = []

    # Heuristic 1: If retreat costs are high, suggest switching cards
    if avg_retreat > 2:
        q1 = (
            select(Card)
            .where(and_(Card.name.is_not(None), Card.name.ilike("%Switch%")))
            .limit(5)
        )
        for c in session.exec(q1).all():
            suggestions.append({"reason": "High retreat → add switching", "card": c})

        q2 = (
            select(Card)
            .where(and_(Card.name.is_not(None), Card.name.ilike("%Escape Rope%")))
            .limit(5)
        )
        for c in session.exec(q2).all():
            suggestions.append({"reason": "High retreat → add switching", "card": c})

    # Heuristic 2: If low supporter density, suggest draw/search Supporters
    if supporter_count < 10:
        q3 = (
            select(Card)
            .where(
                and_(Card.rules_text.is_not(None), Card.rules_text.ilike("%Supporter%"))
            )
            .limit(10)
        )
        for c in session.exec(q3).all():
            suggestions.append(
                {"reason": "Low Supporter density → add draw/search", "card": c}
            )

    # Heuristic 3: If no stadiums, suggest adding one
    if not has_stadium:
        q4 = (
            select(Card)
            .where(
                and_(Card.rules_text.is_not(None), Card.rules_text.ilike("%Stadium%"))
            )
            .limit(10)
        )
        for c in session.exec(q4).all():
            suggestions.append(
                {"reason": "No stadiums → add stadium control", "card": c}
            )

    # Deduplicate by card id
    seen = set()
    uniq = []
    for s in suggestions:
        cid = getattr(s["card"], "id", None)
        if not cid or cid in seen:
            continue
        seen.add(cid)
        uniq.append(s)

    # Return only up to the requested limit
    return uniq[:limit]
