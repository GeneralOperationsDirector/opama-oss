import React, { useState } from "react";
import Button from "../../shared/atoms/Button";
import { DollarSign, Repeat } from "lucide-react";

interface QuickSaleModalProps {
  item: {
    id: number;
    card_id: string;
    card_name?: string;
    quantity: number;
    condition: string | null;
    purchase_price_per_card: number | null;
  };
  mode: "sale" | "trade";
  onClose: () => void;
  onConfirm: (data: any) => Promise<void>;
}

export default function QuickSaleModal({ item, mode, onClose, onConfirm }: QuickSaleModalProps) {
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({
    quantity_sold: Math.min(1, item.quantity),
    sale_price: "",
    fees: "",
    platform: mode === "trade" ? "Trade" : "eBay",
    sale_date: new Date().toISOString().split("T")[0],
    trade_details: "",
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);

    try {
      const salePrice = mode === "trade"
        ? 0 // Trades have no cash value in sale record
        : parseFloat(formData.sale_price || "0");

      await onConfirm({
        quantity_sold: formData.quantity_sold,
        sale_price: salePrice,
        fees: parseFloat(formData.fees || "0"),
        platform: formData.platform,
        sale_date: formData.sale_date,
        trade_details: mode === "trade" ? formData.trade_details : undefined,
      });

      onClose();
    } catch (err) {
      console.error("Failed to record:", err);
    } finally {
      setSaving(false);
    }
  };

  const netProceeds = mode === "sale" && formData.sale_price
    ? parseFloat(formData.sale_price) - parseFloat(formData.fees || "0")
    : 0;

  const purchaseCost = (item.purchase_price_per_card || 0) * formData.quantity_sold;
  const estimatedGain = mode === "sale" ? netProceeds - purchaseCost : 0;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 rounded-lg border border-gray-700 max-w-md w-full">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-700">
          <div className="flex items-center gap-2">
            {mode === "trade" ? (
              <Repeat className="w-5 h-5 text-blue-400" />
            ) : (
              <DollarSign className="w-5 h-5 text-green-400" />
            )}
            <h2 className="text-lg font-bold text-white">
              {mode === "trade" ? "Record Trade" : "Record Sale"}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          {/* Card Info */}
          <div className="bg-gray-800 rounded p-3 border border-gray-700">
            <div className="font-medium text-white">
              {item.card_name || item.card_id}
            </div>
            <div className="text-xs text-gray-400 mt-1">
              {item.condition || "Unknown"} · Available: x{item.quantity}
            </div>
            {item.purchase_price_per_card && (
              <div className="text-xs text-gray-500 mt-1">
                Cost basis: ${item.purchase_price_per_card.toFixed(2)} per card
              </div>
            )}
          </div>

          {/* Quantity */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Quantity {mode === "trade" ? "Traded" : "Sold"}
            </label>
            <input
              type="number"
              min="1"
              max={item.quantity}
              required
              value={formData.quantity_sold}
              onChange={(e) =>
                setFormData({ ...formData, quantity_sold: parseInt(e.target.value) || 1 })
              }
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:border-blue-500 focus:outline-none"
            />
          </div>

          {mode === "sale" ? (
            <>
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
                  onChange={(e) => setFormData({ ...formData, sale_price: e.target.value })}
                  placeholder="0.00"
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:border-blue-500 focus:outline-none"
                />
              </div>

              {/* Fees */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  Fees (shipping, platform fees, etc.)
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={formData.fees}
                  onChange={(e) => setFormData({ ...formData, fees: e.target.value })}
                  placeholder="0.00"
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:border-blue-500 focus:outline-none"
                />
              </div>

              {/* Platform */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  Platform
                </label>
                <select
                  value={formData.platform}
                  onChange={(e) => setFormData({ ...formData, platform: e.target.value })}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:border-blue-500 focus:outline-none"
                >
                  <option value="eBay">eBay</option>
                  <option value="TCGPlayer">TCGPlayer</option>
                  <option value="Cardmarket">Cardmarket</option>
                  <option value="Local">Local Sale</option>
                  <option value="Other">Other</option>
                </select>
              </div>
            </>
          ) : (
            <>
              {/* Trade Details */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  What did you trade for?
                </label>
                <textarea
                  required
                  value={formData.trade_details}
                  onChange={(e) => setFormData({ ...formData, trade_details: e.target.value })}
                  placeholder="e.g., Charizard VMAX + $20 cash"
                  rows={3}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:border-blue-500 focus:outline-none resize-none"
                />
              </div>
            </>
          )}

          {/* Date */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Date
            </label>
            <input
              type="date"
              required
              value={formData.sale_date}
              onChange={(e) => setFormData({ ...formData, sale_date: e.target.value })}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:border-blue-500 focus:outline-none"
            />
          </div>

          {/* Calculation Summary (Sale only) */}
          {mode === "sale" && formData.sale_price && (
            <div className="bg-gray-800 rounded p-3 border border-gray-700">
              <div className="text-xs text-gray-400 mb-2">Calculation</div>
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
                {item.purchase_price_per_card && (
                  <>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Cost Basis:</span>
                      <span className="text-white">${purchaseCost.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between border-t border-gray-700 pt-1">
                      <span className={`font-medium ${estimatedGain >= 0 ? "text-green-400" : "text-red-400"}`}>
                        {estimatedGain >= 0 ? "Gain" : "Loss"}:
                      </span>
                      <span className={`font-bold ${estimatedGain >= 0 ? "text-green-400" : "text-red-400"}`}>
                        {estimatedGain >= 0 ? "+" : ""}${estimatedGain.toFixed(2)}
                      </span>
                    </div>
                  </>
                )}
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-2 pt-2">
            <Button
              type="button"
              variant="ghost"
              onClick={onClose}
              className="flex-1"
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              loading={saving}
              className="flex-1"
            >
              {mode === "trade" ? "Record Trade" : "Record Sale"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
