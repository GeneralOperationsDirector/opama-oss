# external_plugins/opama_portfolio/valuation.py
"""
Portfolio valuation service - core business logic.

Handles:
- Calculating portfolio values from inventory
- Integrating manual prices with market data
- Condition-based price adjustments
- Grading premiums (future)
"""

from typing import Optional, Dict
from decimal import Decimal
from datetime import datetime, date, timedelta
from sqlmodel import Session, select

from opama_pokemon_tcg.inventory.models import InventoryItem
from opama_pokemon_tcg.catalog.models import Card, Set
from .models import (
    MarketPrice,
    PortfolioSnapshot,
)

# Condition multipliers for raw (ungraded) cards
# Based on industry standards for card pricing
CONDITION_MULTIPLIERS = {
    "NM": Decimal("1.00"),    # Near Mint - full price
    "LP": Decimal("0.85"),    # Lightly Played - 15% discount
    "MP": Decimal("0.65"),    # Moderately Played - 35% discount
    "HP": Decimal("0.45"),    # Heavily Played - 55% discount
    "DMG": Decimal("0.25"),   # Damaged - 75% discount
}

# Grading premiums (multiplier over base NM price)
GRADING_MULTIPLIERS = {
    "PSA10": Decimal("3.0"),
    "PSA9": Decimal("1.5"),
    "PSA8": Decimal("1.1"),
    "BGS10": Decimal("7.0"),   # Black Label
    "BGS9.5": Decimal("2.5"),
    "BGS9": Decimal("1.4"),
    "CGC10": Decimal("2.5"),
    "CGC9.5": Decimal("1.6"),
}


def get_effective_price(
    card_id: str,
    condition: str,
    session: Session,
    is_graded: bool = False,
    grade: Optional[str] = None,
) -> tuple[Decimal, str, Optional[int]]:
    """
    Get the effective price for a card, prioritizing:
    1. Manual override (if set)
    2. Market price (if available)
    3. Fallback to $0.00

    Returns:
        (price, source, confidence_score)
        - price: Decimal price
        - source: "manual", "market", "default"
        - confidence_score: 0-100 or None
    """
    # Look for existing market price record
    stmt = select(MarketPrice).where(
        MarketPrice.card_id == card_id,
        MarketPrice.condition == condition,
        MarketPrice.is_graded == is_graded,
    )
    if is_graded and grade:
        stmt = stmt.where(MarketPrice.grade == grade)

    market_price_record = session.exec(stmt).first()

    if market_price_record:
        # Prioritize manual override
        if market_price_record.manual_override is not None:
            return (
                market_price_record.manual_override,
                "manual",
                100,  # Full confidence in user input
            )

        # Use market price
        if market_price_record.market_price is not None:
            return (
                market_price_record.market_price,
                market_price_record.source,
                market_price_record.confidence_score,
            )

    # Fallback to $0.00
    return (Decimal("0.00"), "default", None)


def apply_condition_multiplier(base_price: Decimal, condition: str) -> Decimal:
    """Apply condition-based price adjustment."""
    multiplier = CONDITION_MULTIPLIERS.get(condition, Decimal("1.00"))
    return base_price * multiplier


def apply_grading_premium(base_price: Decimal, grade: str) -> Decimal:
    """
    Calculate premium for graded cards.

    Returns the total value (not just the premium).
    For example, PSA 10 returns 3x the base price.
    """
    multiplier = GRADING_MULTIPLIERS.get(grade, Decimal("1.0"))
    return base_price * multiplier


def calculate_portfolio_value(
    user_id: int,
    session: Session,
    use_purchase_prices: bool = False,
) -> Dict:
    """
    Calculate the current value of a user's portfolio.

    Args:
        user_id: User to calculate for
        session: Database session
        use_purchase_prices: If True, uses purchase_price from inventory
                            If False, uses market prices

    Returns:
        Dictionary with portfolio value details
    """
    # Get user's inventory with card details
    stmt = (
        select(InventoryItem, Card, Set)
        .join(Card, InventoryItem.card_id == Card.id)
        .join(Set, Card.set_id == Set.id)
        .where(InventoryItem.user_id == user_id)
        .where(InventoryItem.quantity > 0)
    )
    results = session.exec(stmt).all()

    total_value = Decimal("0.00")
    total_cost = Decimal("0.00")
    total_items = 0
    unique_cards = 0

    condition_breakdown = {}
    valuations = []

    for inv_item, card, card_set in results:
        quantity = inv_item.quantity
        condition = inv_item.condition or "NM"

        # Calculate unit price
        if use_purchase_prices and inv_item.purchase_price_per_card:
            # Use manual purchase price
            unit_price = Decimal(str(inv_item.purchase_price_per_card))
            price_source = "manual"
            confidence = 100
        else:
            # Use market price
            unit_price, price_source, confidence = get_effective_price(
                card.id,
                condition,
                session,
            )

            # If no market price and inventory has purchase price, use that
            if unit_price == Decimal("0.00") and inv_item.purchase_price_per_card:
                unit_price = Decimal(str(inv_item.purchase_price_per_card))
                price_source = "manual_fallback"
                confidence = 100

        # Calculate purchase cost (for unrealized gain)
        purchase_cost = Decimal("0.00")
        if inv_item.purchase_price_per_card:
            purchase_cost = Decimal(str(inv_item.purchase_price_per_card)) * quantity

        # Calculate item value
        item_value = unit_price * quantity

        total_value += item_value
        total_cost += purchase_cost
        total_items += quantity
        unique_cards += 1

        # Track by condition
        if condition not in condition_breakdown:
            condition_breakdown[condition] = {
                "count": 0,
                "value": Decimal("0.00"),
            }
        condition_breakdown[condition]["count"] += quantity
        condition_breakdown[condition]["value"] += item_value

        # Build valuation record
        unrealized_gain = None
        unrealized_gain_pct = None
        if purchase_cost > 0:
            unrealized_gain = item_value - purchase_cost
            unrealized_gain_pct = (unrealized_gain / purchase_cost) * Decimal("100")

        valuations.append({
            "card_id": card.id,
            "card_name": card.name,
            "set_id": card_set.id,
            "set_name": card_set.name,
            "quantity": quantity,
            "condition": condition,
            "unit_price": unit_price,
            "total_value": item_value,
            "purchase_price": purchase_cost / quantity if purchase_cost > 0 else None,
            "unrealized_gain": unrealized_gain,
            "unrealized_gain_pct": unrealized_gain_pct,
            "price_source": price_source,
            "confidence_score": confidence,
        })

    # Calculate percentages for breakdown
    for cond_data in condition_breakdown.values():
        if total_value > 0:
            cond_data["percentage"] = (cond_data["value"] / total_value) * Decimal("100")
        else:
            cond_data["percentage"] = Decimal("0.00")

    # Sort valuations by total value (highest first)
    valuations.sort(key=lambda x: x["total_value"], reverse=True)

    # Calculate unrealized gain
    unrealized_gain = total_value - total_cost
    unrealized_gain_pct = None
    if total_cost > 0:
        unrealized_gain_pct = (unrealized_gain / total_cost) * Decimal("100")

    return {
        "user_id": user_id,
        "total_value": total_value,
        "total_cost": total_cost,
        "unrealized_gain": unrealized_gain,
        "unrealized_gain_pct": unrealized_gain_pct,
        "total_items": total_items,
        "unique_cards": unique_cards,
        "condition_breakdown": condition_breakdown,
        "valuations": valuations,
        "calculated_at": datetime.utcnow(),
    }


def create_portfolio_snapshot(
    user_id: int,
    session: Session,
    snapshot_type: str = "manual",
) -> PortfolioSnapshot:
    """
    Create a point-in-time snapshot of portfolio value.

    Args:
        user_id: User to snapshot
        session: Database session
        snapshot_type: "manual", "auto_daily", "auto_weekly"

    Returns:
        Created PortfolioSnapshot
    """
    portfolio_data = calculate_portfolio_value(user_id, session)

    # Calculate condition-specific values
    breakdown = portfolio_data["condition_breakdown"]
    graded_value = Decimal("0.00")
    nm_value = breakdown.get("NM", {}).get("value", Decimal("0.00"))
    lp_value = breakdown.get("LP", {}).get("value", Decimal("0.00"))
    mp_value = breakdown.get("MP", {}).get("value", Decimal("0.00"))
    played_value = (
        breakdown.get("HP", {}).get("value", Decimal("0.00"))
        + breakdown.get("DMG", {}).get("value", Decimal("0.00"))
    )

    # TODO: Track graded cards separately when grading is implemented

    # Find top card and set
    valuations = portfolio_data["valuations"]
    top_card = valuations[0] if valuations else None

    # Group by set to find top set
    set_values = {}
    for v in valuations:
        set_id = v["set_id"]
        if set_id not in set_values:
            set_values[set_id] = Decimal("0.00")
        set_values[set_id] += v["total_value"]

    top_set_id = None
    top_set_value = None
    if set_values:
        top_set_id = max(set_values, key=set_values.get)
        top_set_value = set_values[top_set_id]

    snapshot = PortfolioSnapshot(
        user_id=user_id,
        snapshot_date=date.today(),
        snapshot_type=snapshot_type,
        total_value=portfolio_data["total_value"],
        total_cost=portfolio_data["total_cost"],
        unrealized_gain=portfolio_data["unrealized_gain"],
        unrealized_gain_pct=portfolio_data["unrealized_gain_pct"],
        total_items=portfolio_data["total_items"],
        unique_cards=portfolio_data["unique_cards"],
        graded_value=graded_value,
        nm_value=nm_value,
        lp_value=lp_value,
        mp_value=mp_value,
        played_value=played_value,
        top_card_id=top_card["card_id"] if top_card else None,
        top_card_value=top_card["total_value"] if top_card else None,
        top_set_id=top_set_id,
        top_set_value=top_set_value,
    )

    session.add(snapshot)
    session.commit()
    session.refresh(snapshot)

    return snapshot


def get_portfolio_history(
    user_id: int,
    session: Session,
    days: int = 90,
) -> Dict:
    """
    Get historical portfolio values.

    Args:
        user_id: User to get history for
        session: Database session
        days: Number of days of history

    Returns:
        Dictionary with snapshots and summary statistics
    """
    cutoff_date = date.today() - timedelta(days=days)

    stmt = (
        select(PortfolioSnapshot)
        .where(PortfolioSnapshot.user_id == user_id)
        .where(PortfolioSnapshot.snapshot_date >= cutoff_date)
        .order_by(PortfolioSnapshot.snapshot_date)
    )
    snapshots = session.exec(stmt).all()

    snapshot_list = [
        {
            "date": s.snapshot_date,
            "total_value": s.total_value,
            "total_items": s.total_items,
            "unrealized_gain": s.unrealized_gain,
        }
        for s in snapshots
    ]

    # Calculate summary stats
    summary = {}
    if snapshots:
        start_snapshot = snapshots[0]
        end_snapshot = snapshots[-1]

        summary = {
            "start_value": start_snapshot.total_value,
            "end_value": end_snapshot.total_value,
            "absolute_change": end_snapshot.total_value - start_snapshot.total_value,
            "percentage_change": (
                ((end_snapshot.total_value - start_snapshot.total_value) / start_snapshot.total_value) * Decimal("100")
                if start_snapshot.total_value > 0
                else Decimal("0.00")
            ),
            "peak_value": max(s.total_value for s in snapshots),
            "trough_value": min(s.total_value for s in snapshots),
        }

    return {
        "user_id": user_id,
        "period": {
            "start_date": cutoff_date,
            "end_date": date.today(),
            "days": days,
        },
        "snapshots": snapshot_list,
        "summary": summary,
    }
