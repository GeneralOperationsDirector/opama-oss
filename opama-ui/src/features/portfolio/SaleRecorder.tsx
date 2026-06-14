import React, { useState, useEffect } from "react";
import Button from "../../shared/atoms/Button";
import { api } from "../../lib/api";
import { Receipt, DollarSign } from "lucide-react";

interface InventoryItem {
  id: number;
  card_id: string;
  card_name?: string;
  quantity: number;
  condition: string | null;
  purchase_price_per_card: number | null;
}

interface SaleRecorderProps {
  userId: number;
  onToast?: (message: string, type?: "success" | "error" | "info") => void;
  onSaleRecorded?: () => void;
}

export default function SaleRecorder({ userId, onToast, onSaleRecorded }: SaleRecorderProps) {
  const [inventory, setInventory] = useState<InventoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [formVisible, setFormVisible] = useState(false);

  const [formData, setFormData] = useState({
    inventory_item_id: "",
    card_id: "",
    card_name: "",
    quantity_sold: 1,
    condition: "NM",
    sale_price: "",
    fees: "",
    platform: "eBay",
    sale_date: new Date().toISOString().split("T")[0],
    currency: "USD",
    purchase_price_per_card: 0,
  });

  useEffect(() => {
    loadInventory();
  }, [userId]);

  const loadInventory = async () => {
    try {
      const data = await api<any[]>(`/inventory/with_cards?user_id=${userId}`);
      const items = data.map((item) => ({
        id: item.inventory.id,
        card_id: item.card?.id || item.inventory.card_id,
        card_name: item.card?.name,
        quantity: item.inventory.quantity,
        condition: item.inventory.condition,
        purchase_price_per_card: item.inventory.purchase_price_per_card,
      }));
      setInventory(items);
    } catch (err) {
      onToast?.("Failed to load inventory", "error");
    }
  };

  const handleSelectCard = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const itemId = parseInt(e.target.value);
    const item = inventory.find((i) => i.id === itemId);

    if (item) {
      setFormData({
        ...formData,
        inventory_item_id: String(itemId),
        card_id: item.card_id,
        card_name: item.card_name || item.card_id,
        condition: item.condition || "NM",
        purchase_price_per_card: item.purchase_price_per_card || 0,
        quantity_sold: Math.min(1, item.quantity),
      });
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      const salePrice = parseFloat(formData.sale_price);
      const fees = parseFloat(formData.fees || "0");
      const netProceeds = salePrice - fees;
      const purchaseCost =
        formData.purchase_price_per_card * formData.quantity_sold;
      const realizedGain = netProceeds - purchaseCost;

      await api("/portfolio/sales", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId,
          card_id: formData.card_id,
          inventory_item_id: formData.inventory_item_id ? parseInt(formData.inventory_item_id) : null,
          quantity_sold: formData.quantity_sold,
          condition: formData.condition,
          sale_price: salePrice,
          fees: fees,
          sale_date: formData.sale_date,
          platform: formData.platform,
        }),
      });

      onToast?.(
        `Sale recorded! ${realizedGain >= 0 ? "Profit" : "Loss"}: $${Math.abs(realizedGain).toFixed(2)}`,
        realizedGain >= 0 ? "success" : "info"
      );

      // Reset form
      setFormData({
        inventory_item_id: "",
        card_id: "",
        card_name: "",
        quantity_sold: 1,
        condition: "NM",
        sale_price: "",
        fees: "",
        platform: "eBay",
        sale_date: new Date().toISOString().split("T")[0],
        currency: "USD",
        purchase_price_per_card: 0,
      });

      setFormVisible(false);
      onSaleRecorded?.();
      loadInventory();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to record sale";
      onToast?.(message, "error");
    } finally {
      setLoading(false);
    }
  };

  const netProceeds =
    formData.sale_price && formData.fees
      ? parseFloat(formData.sale_price) - parseFloat(formData.fees)
      : formData.sale_price
      ? parseFloat(formData.sale_price)
      : 0;

  const purchaseCost = formData.purchase_price_per_card * formData.quantity_sold;
  const estimatedGain = netProceeds - purchaseCost;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white">Record Sale</h2>
          <p className="text-sm text-gray-400 mt-1">
            Track sales and calculate realized gains/losses
          </p>
        </div>
        <Button
          variant="primary"
          onClick={() => setFormVisible(!formVisible)}
        >
          <Receipt className="w-4 h-4" />
          {formVisible ? "Cancel" : "New Sale"}
        </Button>
      </div>

      {/* Sale Form */}
      {formVisible && (
        <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
          <h3 className="text-lg font-bold text-white mb-4">Sale Details</h3>
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Select Card from Inventory */}
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Select Card from Inventory
              </label>
              <select
                required
                value={formData.inventory_item_id}
                onChange={handleSelectCard}
                className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded text-white focus:border-blue-500 focus:outline-none"
              >
                <option value="">— Choose a card —</option>
                {inventory.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.card_name || item.card_id} · {item.condition || "Unknown"} · x
                    {item.quantity}
                    {item.purchase_price_per_card
                      ? ` · Bought for $${item.purchase_price_per_card.toFixed(2)}`
                      : ""}
                  </option>
                ))}
              </select>
              {formData.card_id && !formData.purchase_price_per_card && (
                <p className="text-xs text-yellow-400 mt-1">
                  ⚠️ No purchase price set for this card. Gain/loss cannot be calculated.
                </p>
              )}
            </div>

            {formData.card_id && (
              <>
                {/* Sale Info Grid */}
                <div className="grid grid-cols-2 gap-4">
                  {/* Quantity Sold */}
                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-1">
                      Quantity Sold
                    </label>
                    <input
                      type="number"
                      min="1"
                      required
                      value={formData.quantity_sold}
                      onChange={(e) =>
                        setFormData({
                          ...formData,
                          quantity_sold: parseInt(e.target.value) || 1,
                        })
                      }
                      className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded text-white focus:border-blue-500 focus:outline-none"
                    />
                  </div>

                  {/* Sale Date */}
                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-1">
                      Sale Date
                    </label>
                    <input
                      type="date"
                      required
                      value={formData.sale_date}
                      onChange={(e) =>
                        setFormData({ ...formData, sale_date: e.target.value })
                      }
                      className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded text-white focus:border-blue-500 focus:outline-none"
                    />
                  </div>

                  {/* Sale Price */}
                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-1">
                      Sale Price ($)
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      required
                      value={formData.sale_price}
                      onChange={(e) =>
                        setFormData({ ...formData, sale_price: e.target.value })
                      }
                      placeholder="0.00"
                      className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded text-white focus:border-blue-500 focus:outline-none"
                    />
                  </div>

                  {/* Fees */}
                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-1">
                      Fees (eBay, shipping, etc.)
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={formData.fees}
                      onChange={(e) =>
                        setFormData({ ...formData, fees: e.target.value })
                      }
                      placeholder="0.00"
                      className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded text-white focus:border-blue-500 focus:outline-none"
                    />
                  </div>

                  {/* Platform */}
                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-1">
                      Platform
                    </label>
                    <select
                      value={formData.platform}
                      onChange={(e) =>
                        setFormData({ ...formData, platform: e.target.value })
                      }
                      className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded text-white focus:border-blue-500 focus:outline-none"
                    >
                      <option value="eBay">eBay</option>
                      <option value="TCGPlayer">TCGPlayer</option>
                      <option value="Cardmarket">Cardmarket</option>
                      <option value="Local">Local Sale</option>
                      <option value="Trade">Trade</option>
                      <option value="Other">Other</option>
                    </select>
                  </div>

                  {/* Currency */}
                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-1">
                      Currency
                    </label>
                    <select
                      value={formData.currency}
                      onChange={(e) =>
                        setFormData({ ...formData, currency: e.target.value })
                      }
                      className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded text-white focus:border-blue-500 focus:outline-none"
                    >
                      <option value="USD">USD</option>
                      <option value="EUR">EUR</option>
                      <option value="GBP">GBP</option>
                      <option value="CAD">CAD</option>
                      <option value="JPY">JPY</option>
                    </select>
                  </div>
                </div>

                {/* Calculation Summary */}
                {formData.sale_price && (
                  <div className="bg-gray-900 rounded-lg p-4 border border-gray-700">
                    <div className="text-sm text-gray-400 mb-2">Calculation Summary</div>
                    <div className="space-y-1 text-sm">
                      <div className="flex justify-between">
                        <span className="text-gray-400">Sale Price:</span>
                        <span className="text-white">${parseFloat(formData.sale_price).toFixed(2)}</span>
                      </div>
                      {formData.fees && (
                        <div className="flex justify-between">
                          <span className="text-gray-400">Fees:</span>
                          <span className="text-red-400">-${parseFloat(formData.fees).toFixed(2)}</span>
                        </div>
                      )}
                      <div className="flex justify-between border-t border-gray-700 pt-1">
                        <span className="text-gray-400">Net Proceeds:</span>
                        <span className="text-white font-medium">${netProceeds.toFixed(2)}</span>
                      </div>
                      {formData.purchase_price_per_card > 0 && (
                        <>
                          <div className="flex justify-between">
                            <span className="text-gray-400">Purchase Cost:</span>
                            <span className="text-white">
                              ${purchaseCost.toFixed(2)}
                            </span>
                          </div>
                          <div className="flex justify-between border-t border-gray-700 pt-1">
                            <span className="text-gray-400 font-medium">
                              Estimated {estimatedGain >= 0 ? "Gain" : "Loss"}:
                            </span>
                            <span
                              className={`font-bold ${
                                estimatedGain >= 0 ? "text-green-400" : "text-red-400"
                              }`}
                            >
                              {estimatedGain >= 0 ? "+" : ""}${estimatedGain.toFixed(2)}
                            </span>
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                )}

                {/* Action Buttons */}
                <div className="flex gap-2 pt-2">
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => setFormVisible(false)}
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
                    <DollarSign className="w-4 h-4" />
                    Record Sale
                  </Button>
                </div>
              </>
            )}
          </form>
        </div>
      )}
    </div>
  );
}
