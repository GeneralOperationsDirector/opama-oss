# Portfolio & Valuation User Guide

## How to Track Your Collection Value

This guide explains how to input market prices and record sales for your Pokemon card collection.

---

## 🎨 **NEW: User-Friendly UI** (Recommended)

You can now manage your portfolio through an easy-to-use web interface instead of curl commands!

### Quick Start with the UI

1. **Edit Purchase Prices** (Inventory Tab)
   - Go to the **Inventory** tab
   - Click the **Edit** button on any card
   - Fill in:
     - Purchase price per card
     - Currency (USD, EUR, GBP, etc.)
     - Acquired from (eBay, TCGPlayer, etc.)
     - Notes (grading, condition details)
   - Click **Save Changes**

2. **Set Market Prices** (Portfolio Tab → Market Prices)
   - Go to the **Portfolio** tab
   - Click **Market Prices** view
   - Click **Add Price** button
   - Fill in:
     - Card ID (e.g., "base1-4")
     - Condition (NM, LP, MP, etc.)
     - Market price
     - Source (manual, TCGPlayer, eBay)
     - Graded card info (optional)
   - Click **Save Price**

3. **Record Sales** (Portfolio Tab → Record Sale)
   - Go to the **Portfolio** tab
   - Click **Record Sale** view
   - Click **New Sale** button
   - Select card from your inventory dropdown
   - Fill in:
     - Quantity sold
     - Sale price
     - Fees (eBay, shipping)
     - Platform (eBay, TCGPlayer, etc.)
     - Sale date
   - See automatic gain/loss calculation
   - Click **Record Sale**

The UI automatically:
- ✅ Pre-fills purchase prices from inventory
- ✅ Calculates total cost
- ✅ Computes net proceeds (sale price - fees)
- ✅ Shows realized gain/loss
- ✅ Updates your portfolio immediately

---

## 📊 Overview

The portfolio system tracks:
1. **Market Prices** - Current estimated values for your cards
2. **Purchase Prices** - What you paid for each card (in inventory)
3. **Sales Transactions** - When you sell cards and realized gains/losses

---

## 💰 Setting Market Prices

Market prices determine the current value of your portfolio. You can set them manually or they'll auto-populate from market data syncs.

### Method 1: API Endpoints (Current Method)

**Set a Market Price**:
```bash
curl -X PUT http://localhost:8008/portfolio/prices \
  -H "Content-Type: application/json" \
  -d '{
    "card_id": "base1-58",
    "condition": "NM",
    "market_price": 50.00,
    "source": "tcgplayer",
    "confidence_score": 85,
    "is_graded": false,
    "grade": null
  }'
```

**Get Market Price for a Card**:
```bash
curl http://localhost:8008/portfolio/prices/base1-58?condition=NM
```

### Method 2: Bulk Import (Coming Soon)

A UI for bulk price updates will be added in future updates.

---

## 🏷️ Adding Purchase Prices to Inventory

When adding cards to your inventory, include the purchase price:

```bash
curl -X POST http://localhost:8008/inventory \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "card_id": "base1-58",
    "quantity": 1,
    "condition": "NM",
    "purchase_price_per_card": 25.50,
    "currency": "USD",
    "acquired_from": "eBay",
    "acquired_at": "2024-01-15"
  }'
```

**Fields Explained**:
- `purchase_price_per_card`: What you paid per card (critical for tracking gains)
- `currency`: USD, EUR, etc. (defaults to USD)
- `acquired_from`: Where you bought it (optional but useful)
- `acquired_at`: Purchase date (optional)

---

## 📝 Recording Sales

When you sell a card, record the transaction to track realized gains:

### API Method

```bash
curl -X POST http://localhost:8008/portfolio/sales \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "card_id": "base1-58",
    "quantity_sold": 1,
    "sale_price": 75.00,
    "fees": 7.50,
    "platform": "eBay",
    "sale_date": "2024-06-15",
    "condition": "NM",
    "currency": "USD"
  }'
```

**Fields Explained**:
- `sale_price`: Total amount received (before fees)
- `fees`: Selling fees (eBay, TCGPlayer, shipping, etc.)
- `platform`: Where you sold it (eBay, TCGPlayer, Local, etc.)
- `sale_date`: When the sale completed
- `condition`: Condition of the card sold

**The system automatically calculates**:
- Net proceeds = sale_price - fees
- Realized gain = net proceeds - (purchase_price × quantity)
- Return % = (realized gain / purchase cost) × 100

---

## 📈 Viewing Your Portfolio

### Portfolio Value
```bash
GET http://localhost:8008/portfolio/1/value
```

Returns:
- **total_value**: Current portfolio value based on market prices
- **total_cost**: Total amount you paid (purchase prices)
- **unrealized_gain**: Current profit/loss (not yet sold)
- **top_holdings**: Your 10 most valuable cards
- **breakdown**: Value by condition (NM, LP, MP, etc.)

### Historical Portfolio Values
```bash
GET http://localhost:8008/portfolio/1/history?days=90
```

Shows how your portfolio value changed over the last 90 days.

### Sales Summary
```bash
GET http://localhost:8008/portfolio/sales/1/summary
```

Returns:
- **total_sales**: Number of cards sold
- **total_proceeds**: Money received from sales
- **total_fees**: Total selling costs
- **total_realized_gain**: Actual profit/loss from sales
- **best_sale**: Your most profitable sale
- **worst_sale**: Your biggest loss

---

## 🎯 Complete Workflow Example

### Step 1: Buy a Card
```bash
# Add to inventory with purchase price
curl -X POST http://localhost:8008/inventory \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "card_id": "base1-4",
    "quantity": 1,
    "condition": "NM",
    "purchase_price_per_card": 200.00,
    "currency": "USD",
    "acquired_from": "TCGPlayer",
    "acquired_at": "2024-01-10"
  }'
```

### Step 2: Set Current Market Price
```bash
# Update market price (current value)
curl -X PUT http://localhost:8008/portfolio/prices \
  -H "Content-Type: application/json" \
  -d '{
    "card_id": "base1-4",
    "condition": "NM",
    "market_price": 350.00,
    "source": "tcgplayer",
    "confidence_score": 90
  }'
```

### Step 3: View Portfolio Value
```bash
# Check your portfolio
curl http://localhost:8008/portfolio/1/value
```

You'll see:
- **Cost**: $200.00 (what you paid)
- **Value**: $350.00 (current market price)
- **Unrealized Gain**: +$150.00 (+75%)

### Step 4: Sell the Card
```bash
# Record the sale
curl -X POST http://localhost:8008/portfolio/sales \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "card_id": "base1-4",
    "quantity_sold": 1,
    "sale_price": 360.00,
    "fees": 36.00,
    "platform": "eBay",
    "sale_date": "2024-06-15",
    "condition": "NM"
  }'
```

Result:
- **Net Proceeds**: $324.00 (360 - 36)
- **Realized Gain**: +$124.00 (324 - 200)
- **Return**: +62%

---

## 💡 Tips for Accurate Tracking

### 1. Always Include Purchase Prices
Without purchase prices, you can't calculate gains:
```bash
# ❌ Bad - no purchase price
"purchase_price_per_card": null

# ✅ Good - tracks your cost
"purchase_price_per_card": 25.50
```

### 2. Update Market Prices Regularly
Market prices change frequently. Update them:
- Weekly for high-value cards ($100+)
- Monthly for mid-range cards ($10-100)
- Quarterly for bulk cards (<$10)

### 3. Track Fees Accurately
Selling fees significantly impact returns:
```bash
# Include ALL fees
"fees": 36.00  # eBay (10%) + PayPal (3%) + shipping ($3)
```

Common fee structures:
- **eBay**: 12.9% final value fee + 3% PayPal
- **TCGPlayer**: 10.25% + 2.5% payment processing
- **Local sales**: 0% (but factor in gas, time)

### 4. Be Consistent with Conditions
Use standard condition grades:
- **NM** (Near Mint) - Looks unplayed
- **LP** (Lightly Played) - Minor wear
- **MP** (Moderately Played) - Noticeable wear
- **HP** (Heavily Played) - Heavy wear
- **DMG** (Damaged) - Creases, tears, writing

### 5. Track Graded Cards Separately
Graded cards have different valuations:
```bash
{
  "card_id": "base1-4",
  "condition": "PSA10",  # Use PSA10, BGS9.5, etc.
  "grade": 10,
  "grading_company": "PSA",
  "is_graded": true,
  "market_price": 2500.00  # Premium over raw
}
```

---

## 📊 Understanding Portfolio Metrics

### Unrealized Gain/Loss
Money you'd make if you sold everything today at current market prices.
- **Positive**: Your collection increased in value
- **Negative**: Your collection decreased in value

**Formula**: Current Value - Total Cost

### Realized Gain/Loss
Actual profit/loss from cards you've sold.
- This is "real" money - you've actually made/lost it
- Appears on your tax returns (if applicable)

**Formula**: Net Proceeds - Purchase Cost

### Return %
Percentage gain/loss on your investment.
- **Unrealized**: (Unrealized Gain / Total Cost) × 100
- **Realized**: (Realized Gain / Total Sales Cost) × 100

### Example
You bought 10 cards for $100 each ($1,000 total):
- Current value: $1,500
- **Unrealized gain**: +$500 (+50%)

You sold 2 cards for $180 each = $360:
- Purchase cost for those 2: $200
- **Realized gain**: +$160 (+80%)

---

## 🔄 Automatic Market Data (Future)

In the future, market prices will auto-sync from:
- TCGPlayer API
- eBay sold listings
- Pokémon TCG API price data

For now, you need to manually set prices or import them.

---

## 🚀 Quick Commands Reference

### Portfolio Value
```bash
# Current portfolio value
GET /portfolio/{user_id}/value

# With manual purchase prices (ignores market data)
GET /portfolio/{user_id}/value?use_purchase_prices=true
```

### Market Prices
```bash
# Set/update price
PUT /portfolio/prices
{
  "card_id": "...",
  "condition": "NM",
  "market_price": 50.00
}

# Get price for a card
GET /portfolio/prices/{card_id}?condition=NM
```

### Sales
```bash
# Record a sale
POST /portfolio/sales
{
  "user_id": 1,
  "card_id": "...",
  "quantity_sold": 1,
  "sale_price": 75.00,
  "fees": 7.50
}

# View all sales
GET /portfolio/sales/{user_id}?limit=50

# Get sales summary
GET /portfolio/sales/{user_id}/summary
```

### Snapshots (Track History)
```bash
# Create a snapshot (saves current portfolio value)
POST /portfolio/{user_id}/snapshot

# View historical values
GET /portfolio/{user_id}/history?days=90
```

---

## 🎓 Best Practices

1. **Snapshot Weekly**: Create snapshots to track value over time
2. **Update After Major Sales**: Keep market prices current
3. **Track Everything**: Include small sales - they add up
4. **Use Consistent Currency**: Stick to one currency (USD recommended)
5. **Back Up Data**: Export your portfolio regularly

---

## ❓ FAQ

**Q: My portfolio value shows $0.00. Why?**
A: You need to either:
- Set market prices for your cards (`PUT /portfolio/prices`)
- Add purchase prices to inventory items (system will fall back to these)

**Q: Can I track cards in different currencies?**
A: Yes! Each item can have its own currency. The system tracks them separately.

**Q: What if I don't know my purchase price?**
A: Use your best estimate or check:
- Old eBay purchase history
- Credit card statements
- TCGPlayer order history

**Q: How do I handle trades (no cash)?**
A: Estimate the value at time of trade:
```bash
# Traded away a card
{
  "sale_price": 50.00,    # Estimated value traded
  "fees": 0.00,           # No cash fees
  "platform": "Trade"
}
```

**Q: Can I track sealed products (booster boxes)?**
A: Yes! Treat each sealed product as a "card":
- Use a descriptive card_id like "sv10-booster-box"
- Track purchase price and current market value
- Record when you open or sell it

---

## 🔮 Coming Soon

Planned features:
- [ ] Web UI for adding market prices
- [ ] Bulk CSV import for prices
- [ ] Auto-sync with TCGPlayer API
- [ ] Price alerts (notify when cards spike)
- [ ] Tax report generation
- [ ] Mobile app for quick sale recording

---

## 📝 Summary

To track your portfolio value:
1. ✅ Add cards to inventory with `purchase_price_per_card`
2. ✅ Set current market prices via `PUT /portfolio/prices`
3. ✅ View portfolio value at `/portfolio/{user_id}/value`
4. ✅ Record sales with `POST /portfolio/sales`
5. ✅ Track history with snapshots

**Your portfolio is only as accurate as the data you input!** Take time to track purchases and update prices regularly.
