# external_plugins/opama_portfolio/schemas.py
"""
Pydantic schemas for portfolio API requests and responses.
"""

from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Portfolio Valuation Responses
# ---------------------------------------------------------------------------

class CardValuation(BaseModel):
    """Individual card valuation within a portfolio."""
    card_id: str
    card_name: str
    set_id: str
    set_name: str

    quantity: int
    condition: str

    # Pricing
    unit_price: Decimal
    total_value: Decimal
    purchase_price: Optional[Decimal] = None
    unrealized_gain: Optional[Decimal] = None
    unrealized_gain_pct: Optional[Decimal] = None

    # Market context
    price_source: str  # manual, tcgplayer, ebay, aggregated
    confidence_score: Optional[int] = None
    price_change_7d: Optional[Decimal] = None
    price_change_30d: Optional[Decimal] = None


class ConditionBreakdown(BaseModel):
    """Value breakdown by card condition."""
    count: int
    value: Decimal
    percentage: Decimal


class PortfolioValueResponse(BaseModel):
    """Current portfolio value and breakdown."""
    user_id: int
    total_value: Decimal
    total_cost: Decimal
    unrealized_gain: Decimal
    unrealized_gain_pct: Optional[Decimal] = None

    currency: str = "USD"
    calculated_at: datetime

    total_items: int
    unique_cards: int

    # Breakdown by condition
    breakdown: dict[str, ConditionBreakdown]

    # Top holdings
    top_holdings: List[CardValuation]

    # Summary stats
    graded_value: Decimal
    graded_count: int


class SnapshotSummary(BaseModel):
    """Summary of a single portfolio snapshot."""
    date: date
    total_value: Decimal
    total_items: int
    unrealized_gain: Optional[Decimal] = None


class PortfolioHistoryResponse(BaseModel):
    """Historical portfolio values."""
    user_id: int
    period: dict  # {start_date, end_date, days}
    snapshots: List[SnapshotSummary]

    summary: dict  # {start_value, end_value, absolute_change, percentage_change, peak_value, etc.}


class BreakdownGroup(BaseModel):
    """Portfolio value grouped by a dimension."""
    group_value: str  # e.g., set_id, rarity value
    value: Decimal
    percentage: Decimal
    item_count: int
    unique_cards: int
    avg_value_per_card: Decimal


class PortfolioBreakdownResponse(BaseModel):
    """Portfolio breakdown by category."""
    user_id: int
    group_by: str  # set, rarity, type, series
    total_value: Decimal
    groups: List[BreakdownGroup]


# ---------------------------------------------------------------------------
# Sale Transaction Schemas
# ---------------------------------------------------------------------------

class CreateSaleRequest(BaseModel):
    """Request to record a card sale. user_id is derived from the auth token."""
    card_id: str
    inventory_item_id: Optional[int] = None

    quantity_sold: int = 1
    condition: str = "NM"

    sale_price: Decimal
    fees: Decimal = Decimal("0.00")

    sale_date: Optional[datetime] = None
    platform: Optional[str] = None  # ebay, tcgplayer, local, trade
    listing_id: Optional[str] = None
    notes: Optional[str] = None


class SaleTransactionResponse(BaseModel):
    """Sale transaction with P&L details."""
    id: int
    user_id: int
    card_id: str
    card_name: str

    quantity_sold: int
    condition: str

    sale_price: Decimal
    unit_price: Decimal
    fees: Decimal
    net_proceeds: Decimal

    original_cost: Decimal
    realized_gain: Decimal
    realized_gain_pct: Optional[Decimal] = None

    sale_date: datetime
    platform: Optional[str] = None
    currency: str = "USD"


class RealizedGainsSummary(BaseModel):
    """Summary of realized gains/losses."""
    user_id: int
    period: Optional[dict] = None  # {start_date, end_date}

    total_sales: int
    total_proceeds: Decimal
    total_fees: Decimal
    net_proceeds: Decimal

    total_cost_basis: Decimal
    total_realized_gain: Decimal
    total_realized_gain_pct: Decimal

    profitable_sales: int
    losing_sales: int
    breakeven_sales: int

    best_sale: Optional[SaleTransactionResponse] = None
    worst_sale: Optional[SaleTransactionResponse] = None


# ---------------------------------------------------------------------------
# Market Price Schemas
# ---------------------------------------------------------------------------

class UpdateMarketPriceRequest(BaseModel):
    """Request to update/override market price."""
    card_id: str
    condition: str = "NM"

    manual_override: Optional[Decimal] = None  # User's manual price

    is_graded: bool = False
    grade: Optional[str] = None


class MarketPriceResponse(BaseModel):
    """Market price data for a card."""
    card_id: str
    condition: str

    market_price: Optional[Decimal] = None
    manual_override: Optional[Decimal] = None
    effective_price: Decimal  # manual_override if set, else market_price

    # Source prices
    tcgplayer_price: Optional[Decimal] = None
    ebay_avg_sold: Optional[Decimal] = None
    ebay_last_sold: Optional[Decimal] = None
    ebay_sale_count: Optional[int] = None

    # Trends
    price_change_7d: Optional[Decimal] = None
    price_change_30d: Optional[Decimal] = None

    source: str
    confidence_score: Optional[int] = None
    last_updated: datetime
