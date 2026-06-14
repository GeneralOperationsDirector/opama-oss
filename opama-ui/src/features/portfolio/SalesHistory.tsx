import React, { useEffect, useState } from "react";
import Button from "../../shared/atoms/Button";
import { Trash2 } from "lucide-react";
import { api } from "../../lib/api";
import type { SaleTransaction, RealizedGainsSummary } from "../../types";

interface SalesHistoryProps {
  userId: number;
  summary: RealizedGainsSummary | null;
  onToast?: (message: string, type?: "success" | "error" | "info") => void;
  onOpenDetails?: (cardId: string) => void;
  onSaleDeleted?: () => void;
}

export default function SalesHistory({ userId, summary, onToast, onOpenDetails, onSaleDeleted }: SalesHistoryProps) {
  const [sales, setSales] = useState<SaleTransaction[]>([]);
  const [loading, setLoading] = useState(false);
  const [limit, setLimit] = useState(10);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const fetchSales = async () => {
    setLoading(true);
    try {
      const data = await api<SaleTransaction[]>(`/portfolio/sales?user_id=${userId}&limit=${limit}`);
      setSales(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load sales history";
      onToast?.(message, "error");
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (saleId: number, cardName: string) => {
    if (!confirm(`Delete sale of "${cardName}"? This will restore the card quantity to your inventory.`)) {
      return;
    }

    setDeletingId(saleId);
    try {
      await api(`/portfolio/sales/${saleId}`, {
        method: "DELETE",
      });
      onToast?.("Sale deleted and inventory restored", "success");

      // Refresh sales list
      await fetchSales();

      // Notify parent to refresh portfolio data
      onSaleDeleted?.();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to delete sale";
      onToast?.(message, "error");
    } finally {
      setDeletingId(null);
    }
  };

  useEffect(() => {
    fetchSales();
  }, [userId, limit]);

  if (!summary) {
    return (
      <div className="bg-gray-800 rounded-lg p-8 border border-gray-700 text-center">
        <div className="text-gray-400 mb-2">No sales history</div>
        <p className="text-sm text-gray-500">
          Record your first sale to start tracking realized gains
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="text-sm text-gray-400 mb-1">Total Sales</div>
          <div className="text-2xl font-bold text-white">{summary.total_sales}</div>
          <div className="text-xs text-gray-500 mt-1">
            {summary.profitable_sales} wins · {summary.losing_sales} losses
          </div>
        </div>

        <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
          <div className="text-sm text-gray-400 mb-1">Total Proceeds</div>
          <div className="text-2xl font-bold text-white">
            ${parseFloat(summary.total_proceeds as any).toFixed(2)}
          </div>
          <div className="text-xs text-gray-500 mt-1">
            Fees: ${parseFloat(summary.total_fees as any).toFixed(2)}
          </div>
        </div>

        <div className={`rounded-lg p-4 border ${
          parseFloat(summary.total_realized_gain as any) >= 0
            ? "bg-green-900/30 border-green-700/50"
            : "bg-red-900/30 border-red-700/50"
        }`}>
          <div className={`text-sm mb-1 ${
            parseFloat(summary.total_realized_gain as any) >= 0 ? "text-green-400" : "text-red-400"
          }`}>
            Net Profit/Loss
          </div>
          <div className="text-2xl font-bold text-white">
            {parseFloat(summary.total_realized_gain as any) >= 0 ? "+" : ""}${parseFloat(summary.total_realized_gain as any).toFixed(2)}
          </div>
          <div className={`text-xs mt-1 ${
            parseFloat(summary.total_realized_gain as any) >= 0 ? "text-green-300/70" : "text-red-300/70"
          }`}>
            {parseFloat(summary.total_realized_gain as any) >= 0 ? "+" : ""}{parseFloat(summary.total_realized_gain_pct as any).toFixed(2)}% return
          </div>
        </div>
      </div>

      {/* Best/Worst Sales */}
      {(summary.best_sale || summary.worst_sale) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {summary.best_sale && (
            <div className="bg-green-900/20 rounded-lg p-4 border border-green-700/50">
              <div className="text-sm font-medium text-green-300 mb-2">🏆 Best Sale</div>
              <div className="font-medium text-white">{summary.best_sale.card_name}</div>
              <div className="text-sm text-gray-400 mt-1">
                Sold for ${parseFloat(summary.best_sale.sale_price as any).toFixed(2)} · Gain: +${parseFloat(summary.best_sale.realized_gain as any).toFixed(2)}
              </div>
            </div>
          )}
          {summary.worst_sale && (
            <div className="bg-red-900/20 rounded-lg p-4 border border-red-700/50">
              <div className="text-sm font-medium text-red-300 mb-2">📉 Worst Sale</div>
              <div className="font-medium text-white">{summary.worst_sale.card_name}</div>
              <div className="text-sm text-gray-400 mt-1">
                Sold for ${parseFloat(summary.worst_sale.sale_price as any).toFixed(2)} · Loss: ${Math.abs(parseFloat(summary.worst_sale.realized_gain as any)).toFixed(2)}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Sales List */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-medium text-white">Recent Sales</h3>
          {sales.length >= limit && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setLimit(limit + 10)}
              loading={loading}
            >
              Load More
            </Button>
          )}
        </div>

        {loading && sales.length === 0 ? (
          <div className="text-center py-8 text-gray-500">Loading sales...</div>
        ) : sales.length === 0 ? (
          <div className="text-center py-8 text-gray-500">No sales recorded yet</div>
        ) : (
          sales.map((sale) => {
            const isProfit = parseFloat(sale.realized_gain as any) >= 0;
            const gainPct = parseFloat(sale.realized_gain_pct as any) || 0;

            return (
              <div
                key={sale.id}
                className="flex items-center justify-between bg-gray-800 rounded-lg p-4 border border-gray-700"
              >
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-white truncate">
                    {sale.card_name}
                  </div>
                  <div className="text-sm text-gray-400 mt-1">
                    {new Date(sale.sale_date).toLocaleDateString()} · {sale.condition} · x{sale.quantity_sold}
                    {sale.platform && ` · ${sale.platform}`}
                  </div>
                </div>

                <div className="flex items-center gap-6 flex-shrink-0">
                  {/* Sale Details */}
                  <div className="text-right">
                    <div className="text-lg font-bold text-white">
                      ${parseFloat(sale.sale_price as any).toFixed(2)}
                    </div>
                    <div className="text-xs text-gray-400">
                      -${parseFloat(sale.fees as any).toFixed(2)} fees
                    </div>
                  </div>

                  {/* P&L */}
                  <div className="text-right min-w-[100px]">
                    <div className={`text-lg font-bold ${
                      isProfit ? "text-green-400" : "text-red-400"
                    }`}>
                      {isProfit ? "+" : ""}${parseFloat(sale.realized_gain as any).toFixed(2)}
                    </div>
                    <div className={`text-xs ${
                      isProfit ? "text-green-300/70" : "text-red-300/70"
                    }`}>
                      {isProfit ? "+" : ""}{gainPct.toFixed(1)}% return
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex flex-col gap-2">
                    {onOpenDetails && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onOpenDetails(sale.card_id)}
                      >
                        View
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDelete(sale.id, sale.card_name)}
                      loading={deletingId === sale.id}
                      className="text-red-500 hover:text-red-600"
                      title="Delete sale and restore inventory"
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
