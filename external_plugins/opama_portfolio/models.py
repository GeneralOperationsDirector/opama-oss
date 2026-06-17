"""
Portfolio and valuation models for tracking card values and sales.

Owned by the `portfolio` plugin (premium tier). Moved out of
services/shared/models_portfolio.py so the portfolio plugin can be
disabled/removed without dragging premium tables into the core schema.

Covers:
- Market price caching (eBay, TCGPlayer, manual overrides)
- Sale transactions (realized gains/losses)
- Portfolio snapshots (historical tracking)
"""

from typing import Optional
from datetime import datetime, date
from decimal import Decimal
from sqlmodel import SQLModel, Field


# ---------------------------------------------------------------------------
# Market Pricing
# ---------------------------------------------------------------------------

class MarketPrice(SQLModel, table=True):
    """
    Cached market price data from various sources.

    Supports manual overrides and multi-source aggregation.

    Attributes:
        card_id: Reference to Card
        condition: Card condition (NM, LP, MP, HP, DMG, PSA10, etc.)
        is_graded: Whether this is a graded card price
        grade: Grading designation (PSA10, BGS9.5, etc.)

        # Pricing
        market_price: Current market price (weighted average of sources)
        manual_override: User-specified price (takes precedence)

        # Source data
        tcgplayer_price: TCGPlayer market price
        ebay_avg_sold: eBay average sold price (last 30 days)
        ebay_last_sold: Most recent eBay sale price
        ebay_sale_count: Number of sales in calculation period

        # Metadata
        source: Primary source (manual, tcgplayer, ebay, aggregated)
        confidence_score: 0-100, how reliable this price is
        last_updated: When this price was last refreshed
        next_refresh: When to refresh (for cache invalidation)
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    # Soft reference: `card` lives in the optional opama_pokemon_tcg external
    # plugin and may not exist in this deployment's schema (e.g. core-only installs).
    card_id: str = Field(index=True)
    condition: str = Field(default="NM", index=True)

    # Grading info
    is_graded: bool = Field(default=False)
    grade: Optional[str] = None

    # Pricing (using Decimal for financial accuracy)
    market_price: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=2)
    manual_override: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=2)

    # Source prices
    tcgplayer_price: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=2)
    ebay_avg_sold: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=2)
    ebay_last_sold: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=2)
    ebay_sale_count: Optional[int] = None

    # Trend indicators
    price_change_7d: Optional[Decimal] = Field(default=None, max_digits=6, decimal_places=2)  # percentage
    price_change_30d: Optional[Decimal] = Field(default=None, max_digits=6, decimal_places=2)

    # Metadata
    source: str = Field(default="manual")  # manual, tcgplayer, ebay, aggregated
    confidence_score: Optional[int] = None  # 0-100
    currency: str = Field(default="USD")

    last_updated: datetime = Field(default_factory=datetime.utcnow)
    next_refresh: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Sales & Liquidation
# ---------------------------------------------------------------------------

class SaleTransaction(SQLModel, table=True):
    """
    Record of a card sale or trade (realized value).

    Tracks the complete lifecycle from acquisition to liquidation,
    enabling profit/loss calculation and portfolio performance analysis.

    Attributes:
        user_id: Seller
        card_id: Card that was sold
        inventory_item_id: Original inventory item (optional, for linking)

        # Sale details
        quantity_sold: How many copies sold
        condition: Condition of sold cards
        sale_price: Total sale price (quantity * unit price)
        unit_price: Price per card
        fees: Platform fees, shipping, etc.
        net_proceeds: sale_price - fees

        # Original acquisition cost (for P&L)
        original_cost: What was originally paid
        realized_gain: net_proceeds - original_cost
        realized_gain_pct: (realized_gain / original_cost) * 100

        # Transaction metadata
        sale_date: When the sale occurred
        platform: Where sold (ebay, tcgplayer, local, trade, etc.)
        buyer_info: Optional buyer reference
        notes: Free-form notes
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    # Ownership/RLS scope (pool tenancy — see pool_vs_silo); nullable through backfill.
    org_id: int = Field(foreign_key="organization.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    # Soft references: `card`/`inventoryitem` live in the optional
    # opama_pokemon_tcg external plugin and may not exist in this
    # deployment's schema (e.g. core-only installs).
    card_id: str = Field(index=True)
    inventory_item_id: Optional[int] = Field(default=None, index=True)

    # Sale details
    quantity_sold: int = Field(default=1)
    condition: str = Field(default="NM")

    # Pricing (Decimal for accuracy)
    sale_price: Decimal = Field(max_digits=10, decimal_places=2)
    unit_price: Decimal = Field(max_digits=10, decimal_places=2)
    fees: Decimal = Field(default=Decimal("0.00"), max_digits=10, decimal_places=2)
    net_proceeds: Decimal = Field(max_digits=10, decimal_places=2)

    # Cost basis & P&L
    original_cost: Decimal = Field(default=Decimal("0.00"), max_digits=10, decimal_places=2)
    realized_gain: Decimal = Field(max_digits=10, decimal_places=2)
    realized_gain_pct: Optional[Decimal] = Field(default=None, max_digits=8, decimal_places=2)

    # Metadata
    sale_date: datetime = Field(default_factory=datetime.utcnow, index=True)
    platform: Optional[str] = None  # ebay, tcgplayer, local, trade
    listing_id: Optional[str] = None  # External platform listing ID
    buyer_info: Optional[str] = None
    notes: Optional[str] = None
    currency: str = Field(default="USD")

    created_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Portfolio Snapshots
# ---------------------------------------------------------------------------

class PortfolioSnapshot(SQLModel, table=True):
    """
    Point-in-time portfolio value snapshot.

    Enables historical tracking and performance analysis.
    Automatically created daily or manually triggered.

    Attributes:
        user_id: Portfolio owner
        snapshot_date: Date of snapshot
        snapshot_type: auto_daily, auto_weekly, manual

        # Aggregate values
        total_value: Total portfolio value (market prices)
        total_cost: Total amount paid (from purchase_price)
        unrealized_gain: total_value - total_cost
        unrealized_gain_pct: (unrealized_gain / total_cost) * 100

        total_items: Number of inventory items
        unique_cards: Number of unique cards

        # Breakdown by condition
        graded_value: Value of graded cards
        nm_value: Near Mint cards value
        lp_value: Lightly Played value
        mp_value: Moderately Played value
        played_value: HP + DMG value

        # Top holdings
        top_card_id: Highest value single card
        top_card_value: Value of top card
        top_set_id: Set with highest total value
        top_set_value: Value of top set
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    # Ownership/RLS scope (pool tenancy — see pool_vs_silo); nullable through backfill.
    org_id: int = Field(foreign_key="organization.id", index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    snapshot_date: date = Field(default_factory=date.today, index=True)
    snapshot_type: str = Field(default="manual")  # manual, auto_daily, auto_weekly

    # Aggregate values
    total_value: Decimal = Field(default=Decimal("0.00"), max_digits=12, decimal_places=2)
    total_cost: Decimal = Field(default=Decimal("0.00"), max_digits=12, decimal_places=2)
    unrealized_gain: Decimal = Field(default=Decimal("0.00"), max_digits=12, decimal_places=2)
    unrealized_gain_pct: Optional[Decimal] = Field(default=None, max_digits=8, decimal_places=2)

    total_items: int = Field(default=0)
    unique_cards: int = Field(default=0)

    # Condition breakdown
    graded_value: Decimal = Field(default=Decimal("0.00"), max_digits=12, decimal_places=2)
    nm_value: Decimal = Field(default=Decimal("0.00"), max_digits=12, decimal_places=2)
    lp_value: Decimal = Field(default=Decimal("0.00"), max_digits=12, decimal_places=2)
    mp_value: Decimal = Field(default=Decimal("0.00"), max_digits=12, decimal_places=2)
    played_value: Decimal = Field(default=Decimal("0.00"), max_digits=12, decimal_places=2)

    # Top holdings
    top_card_id: Optional[str] = None
    top_card_value: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=2)
    top_set_id: Optional[str] = None
    top_set_value: Optional[Decimal] = Field(default=None, max_digits=12, decimal_places=2)

    currency: str = Field(default="USD")
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# User Portfolio Settings
# ---------------------------------------------------------------------------

class UserPortfolioSettings(SQLModel, table=True):
    """
    User preferences for portfolio calculations and display.

    Attributes:
        user_id: Primary key (one-to-one with User)
        default_currency: Preferred currency for display
        auto_snapshot_enabled: Whether to create daily snapshots
        prefer_manual_prices: Use manual overrides over market prices
        include_zero_cost_items: Include items with no purchase_price in totals
        cost_basis_method: FIFO, LIFO, Average (for multi-purchase tracking)
    """

    user_id: int = Field(primary_key=True, foreign_key="user.id")
    # Ownership/RLS scope (pool tenancy — see pool_vs_silo). Settings stay keyed by
    # user (one row per user); org_id denormalizes the owning org for RLS. Nullable
    # through backfill.
    org_id: int = Field(foreign_key="organization.id", index=True)

    default_currency: str = Field(default="USD")
    auto_snapshot_enabled: bool = Field(default=True)
    prefer_manual_prices: bool = Field(default=False)
    include_zero_cost_items: bool = Field(default=True)
    cost_basis_method: str = Field(default="FIFO")  # FIFO, LIFO, Average

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
