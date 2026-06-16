"""
AI tools for the Pokémon TCG Inventory plugin.

Exposes read-only tools so the AI assistant (and MCP clients) can query the
user's Pokémon card collection without touching the CustomAsset table.
"""
from __future__ import annotations

from sqlmodel import Session, select

from services.shared.llm import ToolSpec
from services.shared.models import User
from services.shared.tool_registry import ToolDefinition
from opama_pokemon_tcg.inventory.models import InventoryItem
from opama_pokemon_tcg.catalog.models import Card


def _list_pokemon_inventory(session: Session, user: User, args: dict):
    q = args.get("q", "").strip().lower()
    limit = min(int(args.get("limit", 50)), 200)

    items = session.exec(
        select(InventoryItem).where(InventoryItem.user_id == user.id)
    ).all()

    card_ids = list({i.card_id for i in items})
    cards = {
        c.id: c
        for c in session.exec(select(Card).where(Card.id.in_(card_ids))).all()
    }

    rows = []
    for inv in items:
        card = cards.get(inv.card_id)
        if q and card and q not in (card.name or "").lower():
            continue
        rows.append({
            "inventory_id": inv.id,
            "card_id": inv.card_id,
            "name": card.name if card else inv.card_id,
            "set_id": card.set_id if card else None,
            "number": card.number if card else None,
            "rarity": card.rarity if card else None,
            "image_small": card.image_small if card else None,
            "quantity": inv.quantity,
            "condition": inv.condition,
            "grade": inv.grade,
            "grading_company": inv.grading_company,
            "is_holo": inv.is_holo,
            "is_reverse_holo": inv.is_reverse_holo,
            "is_alt_art": inv.is_alt_art,
            "purchase_price_per_card": inv.purchase_price_per_card,
            "currency": inv.currency,
            "acquired_from": inv.acquired_from,
            "notes": inv.notes,
        })

    return rows[:limit]


def _get_pokemon_inventory_summary(session: Session, user: User, args: dict):
    items = session.exec(
        select(InventoryItem).where(InventoryItem.user_id == user.id)
    ).all()

    total_unique = len(items)
    total_cards = sum(i.quantity or 1 for i in items)
    total_cost = sum(
        (i.purchase_price_per_card or 0) * (i.quantity or 1)
        for i in items
        if i.purchase_price_per_card is not None
    )
    graded = [i for i in items if i.grade is not None]

    return {
        "total_unique_entries": total_unique,
        "total_cards": total_cards,
        "total_purchase_cost": round(total_cost, 2),
        "graded_card_count": len(graded),
    }


TOOLS = [
    ToolDefinition(
        spec=ToolSpec(
            name="list_pokemon_inventory",
            description=(
                "List the user's Pokémon TCG card inventory, joined with card details "
                "(name, set, rarity, image). Optionally filter by card name."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "q": {"type": "string", "description": "Search term matched against card name (case-insensitive)"},
                    "limit": {"type": "integer", "description": "Max results to return (default 50, max 200)", "default": 50},
                },
            },
        ),
        handler=_list_pokemon_inventory,
        mutating=False,
    ),
    ToolDefinition(
        spec=ToolSpec(
            name="get_pokemon_inventory_summary",
            description=(
                "Get aggregate totals for the user's Pokémon TCG inventory: "
                "total unique entries, total card count, total purchase cost, and graded card count."
            ),
            parameters={"type": "object", "properties": {}},
        ),
        handler=_get_pokemon_inventory_summary,
        mutating=False,
    ),
]
