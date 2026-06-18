# external_plugins/opama_portfolio/router.py
"""
Portfolio API router - exposes valuation and tracking endpoints.

All endpoints operate on the authenticated user (derived from the auth
token via get_current_user) - there is no user_id query/path param.

Endpoints:
- GET /portfolio/value - Current portfolio value
- GET /portfolio/history - Historical values
- GET /portfolio/breakdown - Breakdown by category
- POST /portfolio/snapshot - Create manual snapshot

- GET /portfolio/sales - List sales
- POST /portfolio/sales - Record a sale
- DELETE /portfolio/sales/{sale_id} - Delete a sale
- GET /portfolio/sales/summary - Realized gains summary

- GET /portfolio/prices/{card_id} - Get market price (public reference data)
- PUT /portfolio/prices - Update market price (auth required)
"""

from typing import Optional, List
from decimal import Decimal
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from sqlalchemy import desc

from services.shared.database import get_session
from services.shared.models import User
from opama_pokemon_tcg.catalog.models import Card
from opama_pokemon_tcg.inventory.models import InventoryItem
from services.auth.middleware import get_current_user
from services.auth.org_context import OrgContext
from services.auth.entitlements import require_tier
from .models import (
    MarketPrice,
    SaleTransaction,
)

from .schemas import (
    PortfolioValueResponse,
    PortfolioHistoryResponse,
    PortfolioBreakdownResponse,
    CreateSaleRequest,
    SaleTransactionResponse,
    RealizedGainsSummary,
    UpdateMarketPriceRequest,
    MarketPriceResponse,
    CardValuation,
    ConditionBreakdown,
    SnapshotSummary,
    BreakdownGroup,
)

from .valuation import (
    calculate_portfolio_value,
    create_portfolio_snapshot,
    get_portfolio_history,
)

router = APIRouter()

# Portfolio is a premium-tier plugin (see plugin.yaml). In the SaaS pool path
# (ENTITLEMENT_MODE=org) every org-scoped endpoint below is gated on the active
# org's plan via this dependency; in the default "license" mode it is a
# pass-through and resolves the active org exactly like get_current_org.
require_portfolio = require_tier("premium", module="portfolio")


# ---------------------------------------------------------------------------
# Portfolio Valuation Endpoints
# ---------------------------------------------------------------------------

@router.get("/value", response_model=PortfolioValueResponse)
def get_portfolio_value(
    use_purchase_prices: bool = Query(False, description="Use manual purchase prices instead of market"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    ctx: OrgContext = Depends(require_portfolio),
):
    """
    Calculate current portfolio value for the active organization.

    Combines inventory data with market prices (or manual purchase prices).

    Query params:
        use_purchase_prices: If true, uses purchase_price from inventory
                           If false, uses market prices (with fallback to purchase_price)
    """
    portfolio_data = calculate_portfolio_value(ctx.org_id, session, use_purchase_prices)

    # Format breakdown for response
    breakdown = {}
    for condition, data in portfolio_data["condition_breakdown"].items():
        breakdown[condition] = ConditionBreakdown(
            count=data["count"],
            value=data["value"],
            percentage=data["percentage"],
        )

    # Top holdings (limit to top 10)
    top_holdings = [
        CardValuation(**v) for v in portfolio_data["valuations"][:10]
    ]

    # Count graded cards
    graded_count = sum(
        1 for v in portfolio_data["valuations"]
        if v.get("condition", "").startswith("PSA") or v.get("condition", "").startswith("BGS")
    )
    graded_value = sum(
        v["total_value"] for v in portfolio_data["valuations"]
        if v.get("condition", "").startswith("PSA") or v.get("condition", "").startswith("BGS")
    )

    return PortfolioValueResponse(
        user_id=current_user.id,
        total_value=portfolio_data["total_value"],
        total_cost=portfolio_data["total_cost"],
        unrealized_gain=portfolio_data["unrealized_gain"],
        unrealized_gain_pct=portfolio_data["unrealized_gain_pct"],
        calculated_at=portfolio_data["calculated_at"],
        total_items=portfolio_data["total_items"],
        unique_cards=portfolio_data["unique_cards"],
        breakdown=breakdown,
        top_holdings=top_holdings,
        graded_value=graded_value,
        graded_count=graded_count,
    )


@router.post("/snapshot")
def create_snapshot(
    snapshot_type: str = Query("manual", description="Snapshot type: manual, auto_daily, auto_weekly"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    ctx: OrgContext = Depends(require_portfolio),
):
    """
    Create a point-in-time snapshot of portfolio value for the active organization.

    Useful for tracking historical performance.
    """
    snapshot = create_portfolio_snapshot(
        ctx.org_id, session, snapshot_type, user_id=current_user.id
    )

    return {
        "id": snapshot.id,
        "user_id": snapshot.user_id,
        "snapshot_date": snapshot.snapshot_date,
        "total_value": snapshot.total_value,
        "total_cost": snapshot.total_cost,
        "unrealized_gain": snapshot.unrealized_gain,
        "message": "Snapshot created successfully",
    }


@router.get("/history", response_model=PortfolioHistoryResponse)
def get_history(
    days: int = Query(90, ge=1, le=365, description="Number of days of history"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    ctx: OrgContext = Depends(require_portfolio),
):
    """
    Get historical portfolio values for the active organization.

    Returns snapshots and summary statistics over the requested period.
    """
    history_data = get_portfolio_history(ctx.org_id, session, days)

    return PortfolioHistoryResponse(
        user_id=current_user.id,
        period=history_data["period"],
        snapshots=[SnapshotSummary(**s) for s in history_data["snapshots"]],
        summary=history_data["summary"],
    )


@router.get("/breakdown", response_model=PortfolioBreakdownResponse)
def get_breakdown(
    group_by: str = Query("set", description="Group by: set, rarity, type, series"),
    top_n: int = Query(10, ge=1, le=50, description="Number of top groups to return"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    ctx: OrgContext = Depends(require_portfolio),
):
    """
    Get portfolio breakdown by category (set, rarity, type, or series)
    for the active organization.

    Useful for understanding portfolio composition and concentration.
    """
    portfolio_data = calculate_portfolio_value(ctx.org_id, session)

    # Group valuations by the requested dimension
    groups_dict = {}
    for v in portfolio_data["valuations"]:
        # Determine group key based on group_by
        if group_by == "set":
            key = v["set_id"]
            group_value = v["set_name"]
        elif group_by == "rarity":
            # Would need to join with Card to get rarity
            key = "Unknown"
            group_value = "Unknown"
        # TODO: Add more grouping options (type, series) with proper joins
        else:
            key = "Unknown"
            group_value = "Unknown"

        if key not in groups_dict:
            groups_dict[key] = {
                "group_value": group_value,
                "value": Decimal("0.00"),
                "item_count": 0,
                "card_ids": set(),
            }

        groups_dict[key]["value"] += v["total_value"]
        groups_dict[key]["item_count"] += v["quantity"]
        groups_dict[key]["card_ids"].add(v["card_id"])

    # Convert to list and calculate percentages
    total_value = portfolio_data["total_value"]
    groups = []
    for group_data in groups_dict.values():
        unique_cards = len(group_data["card_ids"])
        avg_value = group_data["value"] / unique_cards if unique_cards > 0 else Decimal("0.00")
        percentage = (group_data["value"] / total_value * Decimal("100")) if total_value > 0 else Decimal("0.00")

        groups.append(BreakdownGroup(
            group_value=group_data["group_value"],
            value=group_data["value"],
            percentage=percentage,
            item_count=group_data["item_count"],
            unique_cards=unique_cards,
            avg_value_per_card=avg_value,
        ))

    # Sort by value (highest first) and limit to top_n
    groups.sort(key=lambda g: g.value, reverse=True)
    groups = groups[:top_n]

    return PortfolioBreakdownResponse(
        user_id=current_user.id,
        group_by=group_by,
        total_value=total_value,
        groups=groups,
    )


# ---------------------------------------------------------------------------
# Sales / Liquidation Tracking
# ---------------------------------------------------------------------------

@router.post("/sales", response_model=SaleTransactionResponse)
def record_sale(
    sale: CreateSaleRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    ctx: OrgContext = Depends(require_portfolio),
):
    """
    Record a card sale and calculate realized gain/loss for the
    active organization.

    Automatically calculates P&L based on inventory purchase price.
    """
    # Verify card exists
    card = session.get(Card, sale.card_id)
    if not card:
        raise HTTPException(404, f"Card {sale.card_id} not found")

    # Get original cost from inventory if available, and verify org ownership
    original_cost = Decimal("0.00")
    if sale.inventory_item_id:
        inv_item = session.get(InventoryItem, sale.inventory_item_id)
        if not inv_item or inv_item.org_id != ctx.org_id:
            raise HTTPException(404, f"Inventory item {sale.inventory_item_id} not found")
        if inv_item.purchase_price_per_card:
            original_cost = Decimal(str(inv_item.purchase_price_per_card)) * sale.quantity_sold

    # Calculate unit price and net proceeds
    unit_price = sale.sale_price / sale.quantity_sold if sale.quantity_sold > 0 else Decimal("0.00")
    net_proceeds = sale.sale_price - sale.fees

    # Calculate realized gain
    realized_gain = net_proceeds - original_cost
    realized_gain_pct = None
    if original_cost > 0:
        realized_gain_pct = (realized_gain / original_cost) * Decimal("100")

    # Create transaction
    transaction = SaleTransaction(
        org_id=ctx.org_id,          # owning organization (tenancy/RLS scope)
        user_id=current_user.id,    # acting/created-by user (audit)
        card_id=sale.card_id,
        inventory_item_id=sale.inventory_item_id,
        quantity_sold=sale.quantity_sold,
        condition=sale.condition,
        sale_price=sale.sale_price,
        unit_price=unit_price,
        fees=sale.fees,
        net_proceeds=net_proceeds,
        original_cost=original_cost,
        realized_gain=realized_gain,
        realized_gain_pct=realized_gain_pct,
        sale_date=sale.sale_date or datetime.utcnow(),
        platform=sale.platform,
        listing_id=sale.listing_id,
        notes=sale.notes,
    )

    session.add(transaction)

    # Update inventory quantity if inventory_item_id provided
    if sale.inventory_item_id:
        inv_item = session.get(InventoryItem, sale.inventory_item_id)
        if inv_item:
            inv_item.quantity -= sale.quantity_sold
            if inv_item.quantity <= 0:
                session.delete(inv_item)
            else:
                session.add(inv_item)

    session.commit()
    session.refresh(transaction)

    return SaleTransactionResponse(
        id=transaction.id,
        user_id=transaction.user_id,
        card_id=transaction.card_id,
        card_name=card.name,
        quantity_sold=transaction.quantity_sold,
        condition=transaction.condition,
        sale_price=transaction.sale_price,
        unit_price=transaction.unit_price,
        fees=transaction.fees,
        net_proceeds=transaction.net_proceeds,
        original_cost=transaction.original_cost,
        realized_gain=transaction.realized_gain,
        realized_gain_pct=transaction.realized_gain_pct,
        sale_date=transaction.sale_date,
        platform=transaction.platform,
    )


@router.get("/sales", response_model=List[SaleTransactionResponse])
def list_sales(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(require_portfolio),
):
    """
    List all sales for the active organization, ordered by sale date (newest first).
    """
    stmt = (
        select(SaleTransaction, Card)
        .join(Card, SaleTransaction.card_id == Card.id)
        .where(SaleTransaction.org_id == ctx.org_id)
        .order_by(desc(SaleTransaction.sale_date))
        .limit(limit)
        .offset(offset)
    )
    results = session.exec(stmt).all()

    return [
        SaleTransactionResponse(
            id=sale.id,
            user_id=sale.user_id,
            card_id=sale.card_id,
            card_name=card.name,
            quantity_sold=sale.quantity_sold,
            condition=sale.condition,
            sale_price=sale.sale_price,
            unit_price=sale.unit_price,
            fees=sale.fees,
            net_proceeds=sale.net_proceeds,
            original_cost=sale.original_cost,
            realized_gain=sale.realized_gain,
            realized_gain_pct=sale.realized_gain_pct,
            sale_date=sale.sale_date,
            platform=sale.platform,
        )
        for sale, card in results
    ]


@router.delete("/sales/{sale_id}")
def delete_sale(
    sale_id: int,
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(require_portfolio),
):
    """
    Delete a sale transaction and restore the inventory quantity.

    Useful for undoing accidental sales or correcting mistakes.
    Restores the quantity to the associated inventory item.
    """
    # Get the sale transaction
    sale = session.get(SaleTransaction, sale_id)
    if not sale or sale.org_id != ctx.org_id:
        raise HTTPException(404, f"Sale transaction {sale_id} not found")

    # If this sale had an inventory item, restore the quantity
    if sale.inventory_item_id:
        inv_item = session.get(InventoryItem, sale.inventory_item_id)
        if inv_item:
            # Restore the quantity
            inv_item.quantity += sale.quantity_sold
            session.add(inv_item)
        else:
            # Inventory item was deleted - recreate it
            # This requires card_id and other details from the sale
            # For now, we'll just warn that we can't restore
            pass

    # Delete the sale transaction
    session.delete(sale)
    session.commit()

    return {
        "success": True,
        "message": "Sale deleted and inventory restored",
        "sale_id": sale_id,
        "quantity_restored": sale.quantity_sold,
    }


@router.get("/sales/summary", response_model=RealizedGainsSummary)
def get_realized_gains_summary(
    days: Optional[int] = Query(None, ge=1, le=3650, description="Optional: limit to last N days"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    ctx: OrgContext = Depends(require_portfolio),
):
    """
    Get summary of realized gains/losses from sales for the active organization.

    Provides overall P&L statistics and identifies best/worst sales.
    """
    stmt = select(SaleTransaction).where(SaleTransaction.org_id == ctx.org_id)

    # Optional date filter
    if days:
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        stmt = stmt.where(SaleTransaction.sale_date >= cutoff_date)

    sales = session.exec(stmt).all()

    if not sales:
        return RealizedGainsSummary(
            user_id=current_user.id,
            total_sales=0,
            total_proceeds=Decimal("0.00"),
            total_fees=Decimal("0.00"),
            net_proceeds=Decimal("0.00"),
            total_cost_basis=Decimal("0.00"),
            total_realized_gain=Decimal("0.00"),
            total_realized_gain_pct=Decimal("0.00"),
            profitable_sales=0,
            losing_sales=0,
            breakeven_sales=0,
        )

    # Calculate aggregates
    total_proceeds = sum(s.sale_price for s in sales)
    total_fees = sum(s.fees for s in sales)
    net_proceeds = sum(s.net_proceeds for s in sales)
    total_cost = sum(s.original_cost for s in sales)
    total_realized_gain = sum(s.realized_gain for s in sales)

    total_realized_gain_pct = Decimal("0.00")
    if total_cost > 0:
        total_realized_gain_pct = (total_realized_gain / total_cost) * Decimal("100")

    # Count profitable/losing sales
    profitable = sum(1 for s in sales if s.realized_gain > 0)
    losing = sum(1 for s in sales if s.realized_gain < 0)
    breakeven = sum(1 for s in sales if s.realized_gain == 0)

    # Find best and worst sales (only if there are multiple sales or appropriate gains/losses)
    best_sale = None
    worst_sale = None
    best_card = None
    worst_card = None

    # Only show best sale if there's at least one profitable sale
    profitable_sales = [s for s in sales if s.realized_gain > 0]
    if profitable_sales:
        best_sale = max(profitable_sales, key=lambda s: s.realized_gain)
        best_card = session.get(Card, best_sale.card_id)

    # Only show worst sale if there's at least one losing sale
    losing_sales = [s for s in sales if s.realized_gain < 0]
    if losing_sales:
        worst_sale = min(losing_sales, key=lambda s: s.realized_gain)
        worst_card = session.get(Card, worst_sale.card_id)

    return RealizedGainsSummary(
        user_id=current_user.id,
        period={"days": days} if days else None,
        total_sales=len(sales),
        total_proceeds=total_proceeds,
        total_fees=total_fees,
        net_proceeds=net_proceeds,
        total_cost_basis=total_cost,
        total_realized_gain=total_realized_gain,
        total_realized_gain_pct=total_realized_gain_pct,
        profitable_sales=profitable,
        losing_sales=losing,
        breakeven_sales=breakeven,
        best_sale=SaleTransactionResponse(
            id=best_sale.id,
            user_id=best_sale.user_id,
            card_id=best_sale.card_id,
            card_name=best_card.name if best_card else "Unknown",
            quantity_sold=best_sale.quantity_sold,
            condition=best_sale.condition,
            sale_price=best_sale.sale_price,
            unit_price=best_sale.unit_price,
            fees=best_sale.fees,
            net_proceeds=best_sale.net_proceeds,
            original_cost=best_sale.original_cost,
            realized_gain=best_sale.realized_gain,
            realized_gain_pct=best_sale.realized_gain_pct,
            sale_date=best_sale.sale_date,
            platform=best_sale.platform,
            currency=best_sale.currency,
        ) if best_sale else None,
        worst_sale=SaleTransactionResponse(
            id=worst_sale.id,
            user_id=worst_sale.user_id,
            card_id=worst_sale.card_id,
            card_name=worst_card.name if worst_card else "Unknown",
            quantity_sold=worst_sale.quantity_sold,
            condition=worst_sale.condition,
            sale_price=worst_sale.sale_price,
            unit_price=worst_sale.unit_price,
            fees=worst_sale.fees,
            net_proceeds=worst_sale.net_proceeds,
            original_cost=worst_sale.original_cost,
            realized_gain=worst_sale.realized_gain,
            realized_gain_pct=worst_sale.realized_gain_pct,
            sale_date=worst_sale.sale_date,
            platform=worst_sale.platform,
            currency=worst_sale.currency,
        ) if worst_sale else None,
    )


# ---------------------------------------------------------------------------
# Market Price Management
# ---------------------------------------------------------------------------

@router.get("/prices/{card_id}", response_model=MarketPriceResponse)
def get_market_price(
    card_id: str,
    condition: str = Query("NM", description="Card condition"),
    session: Session = Depends(get_session),
):
    """
    Get market price data for a card.

    Returns manual overrides, market prices, and trend data.
    """
    # Verify card exists
    card = session.get(Card, card_id)
    if not card:
        raise HTTPException(404, f"Card {card_id} not found")

    # Look for price record
    stmt = select(MarketPrice).where(
        MarketPrice.card_id == card_id,
        MarketPrice.condition == condition,
    )
    price_record = session.exec(stmt).first()

    if not price_record:
        # Return default response
        return MarketPriceResponse(
            card_id=card_id,
            condition=condition,
            effective_price=Decimal("0.00"),
            source="default",
            last_updated=datetime.utcnow(),
        )

    # Determine effective price
    effective_price = price_record.manual_override or price_record.market_price or Decimal("0.00")

    return MarketPriceResponse(
        card_id=price_record.card_id,
        condition=price_record.condition,
        market_price=price_record.market_price,
        manual_override=price_record.manual_override,
        effective_price=effective_price,
        tcgplayer_price=price_record.tcgplayer_price,
        ebay_avg_sold=price_record.ebay_avg_sold,
        ebay_last_sold=price_record.ebay_last_sold,
        ebay_sale_count=price_record.ebay_sale_count,
        price_change_7d=price_record.price_change_7d,
        price_change_30d=price_record.price_change_30d,
        source=price_record.source,
        confidence_score=price_record.confidence_score,
        last_updated=price_record.last_updated,
    )


@router.put("/prices", response_model=MarketPriceResponse)
def update_market_price(
    price_update: UpdateMarketPriceRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Update or set a manual price override for a card.

    Allows users to manually specify card values when market data is unavailable
    or when they disagree with automated valuations. Requires authentication
    since this writes to shared price data used by all users.
    """
    # Verify card exists
    card = session.get(Card, price_update.card_id)
    if not card:
        raise HTTPException(404, f"Card {price_update.card_id} not found")

    # Find or create price record
    stmt = select(MarketPrice).where(
        MarketPrice.card_id == price_update.card_id,
        MarketPrice.condition == price_update.condition,
        MarketPrice.is_graded == price_update.is_graded,
    )
    price_record = session.exec(stmt).first()

    if not price_record:
        # Create new record
        price_record = MarketPrice(
            card_id=price_update.card_id,
            condition=price_update.condition,
            is_graded=price_update.is_graded,
            grade=price_update.grade,
            manual_override=price_update.manual_override,
            source="manual",
        )
    else:
        # Update existing
        price_record.manual_override = price_update.manual_override
        price_record.last_updated = datetime.utcnow()
        if price_update.manual_override:
            price_record.source = "manual"

    session.add(price_record)
    session.commit()
    session.refresh(price_record)

    effective_price = price_record.manual_override or price_record.market_price or Decimal("0.00")

    return MarketPriceResponse(
        card_id=price_record.card_id,
        condition=price_record.condition,
        market_price=price_record.market_price,
        manual_override=price_record.manual_override,
        effective_price=effective_price,
        source=price_record.source,
        confidence_score=price_record.confidence_score or 100 if price_record.manual_override else None,
        last_updated=price_record.last_updated,
    )
