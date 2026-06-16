import React, { useState } from "react";
import Button from "../../shared/atoms/Button";

interface EditInventoryModalProps {
  item: {
    id: number;
    card_id: string;
    card_name?: string;
    quantity: number;
    condition: string | null;
    purchase_price_per_card: number | null;
    currency: string | null;
    acquired_from: string | null;
    notes: string | null;
  };
  onClose: () => void;
  onSave: (updates: any) => Promise<void>;
}

export default function EditInventoryModal({ item, onClose, onSave }: EditInventoryModalProps) {
  const [formData, setFormData] = useState({
    purchase_price_per_card: item.purchase_price_per_card || "",
    currency: item.currency || "USD",
    acquired_from: item.acquired_from || "",
    notes: item.notes || "",
  });
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      // Build update payload, only including non-empty values
      const updates: any = {};

      if (formData.purchase_price_per_card) {
        updates.purchase_price_per_card = parseFloat(formData.purchase_price_per_card as any);
      }

      if (formData.currency) {
        updates.currency = formData.currency;
      }

      if (formData.acquired_from) {
        updates.acquired_from = formData.acquired_from;
      }

      if (formData.notes) {
        updates.notes = formData.notes;
      }

      await onSave(updates);
      onClose();
    } catch (err) {
      console.error("Failed to save:", err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 rounded-lg border border-gray-700 max-w-md w-full">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-700">
          <h2 className="text-lg font-bold text-white">Set Card Value</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          {/* Card Info (Read-only) */}
          <div>
            <div className="text-sm font-medium text-gray-400 mb-1">Card</div>
            <div className="text-white font-medium">
              {item.card_name || item.card_id}
            </div>
            <div className="text-xs text-gray-500">
              {item.condition || "Unknown condition"} · x{item.quantity}
            </div>
          </div>

          {/* Cost Basis / Value */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Cost Basis / Acquisition Value (per card)
            </label>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
                  $
                </span>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={formData.purchase_price_per_card}
                  onChange={(e) =>
                    setFormData({ ...formData, purchase_price_per_card: e.target.value as any })
                  }
                  placeholder="0.00"
                  className="w-full pl-7 pr-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:border-blue-500 focus:outline-none"
                />
              </div>
              <select
                value={formData.currency}
                onChange={(e) => setFormData({ ...formData, currency: e.target.value })}
                className="px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:border-blue-500 focus:outline-none"
              >
                <option value="USD">USD</option>
                <option value="EUR">EUR</option>
                <option value="GBP">GBP</option>
                <option value="JPY">JPY</option>
                <option value="CAD">CAD</option>
              </select>
            </div>
            <p className="text-xs text-gray-500 mt-1">
              What you paid, traded, or estimated value if pulled from pack
            </p>
            <p className="text-xs text-gray-500">
              Total value: $
              {formData.purchase_price_per_card
                ? (parseFloat(formData.purchase_price_per_card as any) * item.quantity).toFixed(2)
                : "0.00"}
            </p>
          </div>

          {/* Acquired From */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Acquired From / Source
            </label>
            <input
              type="text"
              value={formData.acquired_from}
              onChange={(e) => setFormData({ ...formData, acquired_from: e.target.value })}
              placeholder="Booster pack, eBay, TCGPlayer, Trade, Gift, etc."
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:border-blue-500 focus:outline-none"
            />
            <p className="text-xs text-gray-500 mt-1">
              How you got this card (store, pack, trade, etc.)
            </p>
          </div>

          {/* Notes */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Notes
            </label>
            <textarea
              value={formData.notes}
              onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
              placeholder="Trade details, pack info, grading, condition notes, etc."
              rows={3}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white focus:border-blue-500 focus:outline-none resize-none"
            />
            <p className="text-xs text-gray-500 mt-1">
              For trades: list what you traded. For pulls: note pack/set info
            </p>
          </div>

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
              Save Changes
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
