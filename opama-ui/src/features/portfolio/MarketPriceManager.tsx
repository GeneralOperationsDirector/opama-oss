import React, { useState, useEffect } from "react";
import Button from "../../shared/atoms/Button";
import { api } from "../../lib/api";
import { Search, DollarSign, TrendingUp } from "lucide-react";

interface MarketPrice {
  card_id: string;
  card_name?: string;
  condition: string;
  market_price: number;
  source: string;
  confidence_score: number;
  is_graded: boolean;
  grade: number | null;
  last_updated: string;
}

interface MarketPriceManagerProps {
  userId: number;
  onToast?: (message: string, type?: "success" | "error" | "info") => void;
}

export default function MarketPriceManager({ userId, onToast }: MarketPriceManagerProps) {
  const [prices, setPrices] = useState<MarketPrice[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [showAddForm, setShowAddForm] = useState(false);

  // Form state
  const [formData, setFormData] = useState({
    card_id: "",
    condition: "NM",
    market_price: "",
    source: "manual",
    confidence_score: 100,
    is_graded: false,
    grade: "",
  });

  const fetchPrices = async () => {
    setLoading(true);
    try {
      // Get all cards from inventory to show which need prices
      const inventory = await api<any[]>(`/inventory/with_cards?user_id=${userId}`);

      // For each card, try to fetch its market price
      const pricePromises = inventory.map(async (item) => {
        try {
          const price = await api<MarketPrice>(
            `/portfolio/prices/${item.card?.id || item.inventory.card_id}?condition=${item.inventory.condition || "NM"}`
          );
          return price;
        } catch {
          return null;
        }
      });

      const results = await Promise.all(pricePromises);
      setPrices(results.filter((p) => p !== null) as MarketPrice[]);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load market prices";
      onToast?.(message, "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPrices();
  }, [userId]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      await api("/portfolio/prices", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          card_id: formData.card_id,
          condition: formData.condition,
          market_price: parseFloat(formData.market_price),
          source: formData.source,
          confidence_score: formData.confidence_score,
          is_graded: formData.is_graded,
          grade: formData.is_graded && formData.grade ? parseInt(formData.grade) : null,
        }),
      });

      onToast?.("Market price updated", "success");
      setShowAddForm(false);
      setFormData({
        card_id: "",
        condition: "NM",
        market_price: "",
        source: "manual",
        confidence_score: 100,
        is_graded: false,
        grade: "",
      });
      fetchPrices();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to update market price";
      onToast?.(message, "error");
    } finally {
      setLoading(false);
    }
  };

  const filteredPrices = prices.filter((p) => {
    const query = searchQuery.toLowerCase();
    return (
      (p.card_name?.toLowerCase().includes(query) || false) ||
      p.card_id.toLowerCase().includes(query)
    );
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white">Market Prices</h2>
          <p className="text-sm text-gray-400 mt-1">
            Set current market values for your collection
          </p>
        </div>
        <Button
          variant="primary"
          onClick={() => setShowAddForm(!showAddForm)}
        >
          <DollarSign className="w-4 h-4" />
          {showAddForm ? "Cancel" : "Add Price"}
        </Button>
      </div>

      {/* Add/Edit Form */}
      {showAddForm && (
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h3 className="text-lg font-bold text-white mb-4">Set Market Price</h3>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              {/* Card ID */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  Card ID
                </label>
                <input
                  type="text"
                  required
                  value={formData.card_id}
                  onChange={(e) => setFormData({ ...formData, card_id: e.target.value })}
                  placeholder="e.g., base1-4"
                  className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded text-white focus:border-blue-500 focus:outline-none"
                />
              </div>

              {/* Condition */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  Condition
                </label>
                <select
                  value={formData.condition}
                  onChange={(e) => setFormData({ ...formData, condition: e.target.value })}
                  className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded text-white focus:border-blue-500 focus:outline-none"
                >
                  <option value="NM">Near Mint (NM)</option>
                  <option value="LP">Lightly Played (LP)</option>
                  <option value="MP">Moderately Played (MP)</option>
                  <option value="HP">Heavily Played (HP)</option>
                  <option value="DMG">Damaged (DMG)</option>
                  <option value="PSA10">PSA 10</option>
                  <option value="PSA9">PSA 9</option>
                  <option value="BGS9.5">BGS 9.5</option>
                </select>
              </div>

              {/* Market Price */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  Market Price ($)
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  required
                  value={formData.market_price}
                  onChange={(e) => setFormData({ ...formData, market_price: e.target.value })}
                  placeholder="0.00"
                  className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded text-white focus:border-blue-500 focus:outline-none"
                />
              </div>

              {/* Source */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  Source
                </label>
                <select
                  value={formData.source}
                  onChange={(e) => setFormData({ ...formData, source: e.target.value })}
                  className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded text-white focus:border-blue-500 focus:outline-none"
                >
                  <option value="manual">Manual Entry</option>
                  <option value="tcgplayer">TCGPlayer</option>
                  <option value="ebay">eBay</option>
                  <option value="cardmarket">Cardmarket</option>
                </select>
              </div>

              {/* Graded */}
              <div className="flex items-center">
                <input
                  type="checkbox"
                  id="is_graded"
                  checked={formData.is_graded}
                  onChange={(e) =>
                    setFormData({ ...formData, is_graded: e.target.checked, grade: "" })
                  }
                  className="w-4 h-4 text-blue-600 bg-gray-900 border-gray-700 rounded focus:ring-blue-500"
                />
                <label htmlFor="is_graded" className="ml-2 text-sm text-gray-300">
                  Graded Card
                </label>
              </div>

              {/* Grade */}
              {formData.is_graded && (
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1">
                    Grade
                  </label>
                  <input
                    type="number"
                    step="0.5"
                    min="1"
                    max="10"
                    value={formData.grade}
                    onChange={(e) => setFormData({ ...formData, grade: e.target.value })}
                    placeholder="10"
                    className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded text-white focus:border-blue-500 focus:outline-none"
                  />
                </div>
              )}
            </div>

            <div className="flex gap-2 pt-2">
              <Button
                type="button"
                variant="ghost"
                onClick={() => setShowAddForm(false)}
                className="flex-1"
              >
                Cancel
              </Button>
              <Button
                type="submit"
                variant="primary"
                loading={loading}
                className="flex-1"
              >
                Save Price
              </Button>
            </div>
          </form>
        </div>
      )}

      {/* Search */}
      <div className="flex items-center gap-2 bg-gray-800 rounded-lg px-4 py-2 border border-gray-700">
        <Search className="w-4 h-4 text-gray-400" />
        <input
          type="text"
          placeholder="Search by card name or ID..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="flex-1 bg-transparent text-white placeholder-gray-400 focus:outline-none"
        />
      </div>

      {/* Prices List */}
      {loading && prices.length === 0 ? (
        <div className="text-center py-8 text-gray-500">Loading prices...</div>
      ) : filteredPrices.length === 0 ? (
        <div className="text-center py-8 bg-gray-800 rounded-lg border border-gray-700">
          <TrendingUp className="w-12 h-12 text-gray-600 mx-auto mb-3" />
          <div className="text-gray-400 mb-2">No market prices set</div>
          <p className="text-sm text-gray-500">
            Click "Add Price" to set market values for your cards
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredPrices.map((price, index) => (
            <div
              key={`${price.card_id}-${price.condition}-${index}`}
              className="flex items-center justify-between bg-gray-800 rounded-lg p-4 border border-gray-700"
            >
              <div className="flex-1">
                <div className="font-medium text-white">
                  {price.card_name || price.card_id}
                </div>
                <div className="text-sm text-gray-400 mt-1">
                  {price.condition}
                  {price.is_graded && price.grade && ` · Grade ${price.grade}`}
                  {" · "}Source: {price.source}
                </div>
              </div>
              <div className="text-right">
                <div className="text-lg font-bold text-white">
                  ${parseFloat(price.market_price as any).toFixed(2)}
                </div>
                <div className="text-xs text-gray-500">
                  {price.confidence_score}% confidence
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
