import React, { useEffect, useState } from "react";
import { RefreshCw, Camera } from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from "recharts";
import { api } from "../../lib/api";
import type { PortfolioValue, PortfolioHistory, RealizedGainsSummary, InvRow } from "../../types";
import ValueSummary from "./ValueSummary";
import TopHoldings from "./TopHoldings";
import HistoricalChart from "./HistoricalChart";
import SalesHistory from "./SalesHistory";
import MarketPriceManager from "./MarketPriceManager";
import SaleRecorder from "./SaleRecorder";
import EditInventoryModal from "../inventory/EditInventoryModal";
import QuickSaleModal from "../inventory/QuickSaleModal";

type ActiveView = "overview" | "history" | "sales" | "prices" | "record-sale";

const VIEWS: { id: ActiveView; label: string }[] = [
  { id: "overview",     label: "Overview" },
  { id: "history",      label: "History" },
  { id: "sales",        label: "Sales" },
  { id: "prices",       label: "Market Prices" },
  { id: "record-sale",  label: "Record Sale" },
];

const BAR_COLORS = ["#f97316","#6366f1","#8b5cf6","#06b6d4","#10b981","#f59e0b","#ec4899","#3b82f6"];

function fmt(n: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(n);
}

interface PortfolioTabProps {
  userId: number;
  onOpenDetails?: (cardId: string) => void;
  onToast?: (message: string, type?: "success" | "error" | "info") => void;
}

export default function PortfolioTab({ userId, onOpenDetails, onToast }: PortfolioTabProps) {
  const [portfolioValue, setPortfolioValue] = useState<PortfolioValue | null>(null);
  const [history, setHistory] = useState<PortfolioHistory | null>(null);
  const [salesSummary, setSalesSummary] = useState<RealizedGainsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeView, setActiveView] = useState<ActiveView>("overview");
  const [snapshotLoading, setSnapshotLoading] = useState(false);
  const [editingItem, setEditingItem] = useState<any>(null);
  const [saleItem, setSaleItem] = useState<{ item: any; mode: "sale" | "trade" } | null>(null);

  const fetchPortfolioData = async () => {
    setLoading(true);
    try {
      const [valueData, historyData, summaryData] = await Promise.all([
        api<PortfolioValue>(`/portfolio/value`),
        api<PortfolioHistory>(`/portfolio/history?days=90`),
        api<RealizedGainsSummary>(`/portfolio/sales/summary`),
      ]);
      setPortfolioValue(valueData);
      setHistory(historyData);
      setSalesSummary(summaryData);
    } catch (err) {
      onToast?.(err instanceof Error ? err.message : "Failed to load portfolio data", "error");
    } finally {
      setLoading(false);
    }
  };

  const handleCreateSnapshot = async () => {
    setSnapshotLoading(true);
    try {
      await api(`/portfolio/snapshot`, { method: "POST" });
      onToast?.("Snapshot created", "success");
      const historyData = await api<PortfolioHistory>(`/portfolio/history?days=90`);
      setHistory(historyData);
    } catch (err) {
      onToast?.(err instanceof Error ? err.message : "Failed to create snapshot", "error");
    } finally {
      setSnapshotLoading(false);
    }
  };

  const resolveInventoryItem = async (cardId: string, condition: string) => {
    const inventory = await api<InvRow[]>(`/inventory/with_cards?user_id=${userId}`);
    const norm = (c: string | null | undefined) => c || null;
    let match = inventory.find(
      (r) => r.inventory.card_id === cardId && norm(r.inventory.condition) === norm(condition)
    );
    if (!match) {
      const cardItems = inventory.filter((r) => r.inventory.card_id === cardId);
      if (cardItems.length === 1) match = cardItems[0];
    }
    return match ?? null;
  };

  const handleEditValue = async (cardId: string, condition: string, cardName: string) => {
    try {
      const match = await resolveInventoryItem(cardId, condition);
      if (match) setEditingItem({ ...match.inventory, card_name: cardName });
      else onToast?.("Could not find inventory item", "error");
    } catch { onToast?.("Failed to load inventory item", "error"); }
  };

  const saveItemEdits = async (updates: any) => {
    if (!editingItem) return;
    try {
      await api(`/inventory/${editingItem.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updates),
      });
      onToast?.("Card value updated", "success");
      setEditingItem(null);
      fetchPortfolioData();
    } catch (err) {
      onToast?.(err instanceof Error ? err.message : "Failed to update card value", "error");
    }
  };

  const handleSold = async (cardId: string, condition: string, cardName: string) => {
    try {
      const match = await resolveInventoryItem(cardId, condition);
      if (match) setSaleItem({ item: { ...match.inventory, card_name: cardName }, mode: "sale" });
      else onToast?.("Could not find inventory item", "error");
    } catch { onToast?.("Failed to load inventory item", "error"); }
  };

  const handleTraded = async (cardId: string, condition: string, cardName: string) => {
    try {
      const match = await resolveInventoryItem(cardId, condition);
      if (match) setSaleItem({ item: { ...match.inventory, card_name: cardName }, mode: "trade" });
      else onToast?.("Could not find inventory item", "error");
    } catch { onToast?.("Failed to load inventory item", "error"); }
  };

  const handleSaleConfirm = async (saleData: any) => {
    if (!saleItem) return;
    try {
      await api("/portfolio/sales", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          card_id: saleItem.item.card_id,
          inventory_item_id: saleItem.item.id,
          quantity_sold: saleData.quantity_sold,
          condition: saleItem.item.condition || "NM",
          sale_price: saleData.sale_price,
          fees: saleData.fees,
          sale_date: saleData.sale_date,
          platform: saleData.platform,
        }),
      });
      onToast?.(
        saleItem.mode === "trade"
          ? `Trade recorded: ${saleData.trade_details}`
          : `Sale recorded! ${saleData.quantity_sold}× sold`,
        "success"
      );
      setSaleItem(null);
      fetchPortfolioData();
    } catch (err) {
      onToast?.(err instanceof Error ? err.message : "Failed to record sale", "error");
    }
  };

  useEffect(() => { fetchPortfolioData(); }, [userId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24 text-slate-400 text-sm">
        Loading portfolio…
      </div>
    );
  }

  if (!portfolioValue) {
    return (
      <div className="py-20 text-center space-y-2">
        <div className="text-3xl">📊</div>
        <div className="text-slate-600 font-medium">No portfolio data available</div>
        <p className="text-sm text-slate-400">
          Add cards to your inventory with purchase prices to see your portfolio value.
        </p>
      </div>
    );
  }

  /* Bar chart data from top holdings */
  const chartData = portfolioValue.top_holdings.slice(0, 8).map((h, i) => ({
    name: h.card_name.length > 14 ? h.card_name.slice(0, 13) + "…" : h.card_name,
    value: parseFloat(h.total_value as any),
    colorIndex: i,
  }));

  return (
    <div className="space-y-5">

      {/* ── Nav bar ── */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex gap-1 flex-wrap">
          {VIEWS.map(({ id, label }) => (
            <button
              key={id}
              onClick={() => setActiveView(id)}
              className={`h-8 px-3 rounded-lg text-sm font-medium transition-colors ${
                activeView === id
                  ? "bg-indigo-50 text-indigo-700 border border-indigo-200"
                  : "text-slate-500 hover:text-slate-800 hover:bg-slate-100"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="flex gap-1.5">
          <button
            onClick={handleCreateSnapshot}
            disabled={snapshotLoading}
            className="h-8 px-3 rounded-lg flex items-center gap-1.5 text-sm font-medium bg-slate-100 hover:bg-slate-200 text-slate-600 border border-slate-200 disabled:opacity-50"
          >
            <Camera className="w-3.5 h-3.5" />
            {snapshotLoading ? "Saving…" : "Snapshot"}
          </button>
          <button
            onClick={fetchPortfolioData}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-slate-400 hover:text-slate-700 hover:bg-slate-100"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* ── Always-visible stat cards ── */}
      <ValueSummary portfolioValue={portfolioValue} salesSummary={salesSummary} />

      {/* ── Overview ── */}
      {activeView === "overview" && (
        <>
          {/* Top holdings bar chart */}
          {chartData.length > 0 && (
            <div className="bg-white rounded-2xl border border-slate-200 p-5">
              <h2 className="text-sm font-semibold text-slate-700 mb-4">Top Holdings by Value</h2>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }} barCategoryGap="30%">
                  <CartesianGrid vertical={false} stroke="#f1f5f9" />
                  <XAxis
                    dataKey="name"
                    tick={{ fontSize: 10, fill: "#94a3b8" }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    tickFormatter={(v) => `$${v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v}`}
                    tick={{ fontSize: 11, fill: "#94a3b8" }}
                    axisLine={false}
                    tickLine={false}
                    width={48}
                  />
                  <Tooltip
                    formatter={(v: number) => [fmt(v), "Value"]}
                    cursor={{ fill: "#f8fafc" }}
                    contentStyle={{ border: "1px solid #e2e8f0", borderRadius: 10, fontSize: 12 }}
                  />
                  <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                    {chartData.map((entry) => (
                      <Cell key={entry.name} fill={BAR_COLORS[entry.colorIndex % BAR_COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Top holdings list */}
          {portfolioValue.top_holdings.length > 0 && (
            <div className="space-y-2">
              <h2 className="text-sm font-semibold text-slate-700">
                Top Holdings <span className="text-slate-400 font-normal">({portfolioValue.top_holdings.length} cards)</span>
              </h2>
              <TopHoldings
                holdings={portfolioValue.top_holdings}
                onOpenDetails={onOpenDetails}
                onEditValue={handleEditValue}
                onSold={handleSold}
                onTraded={handleTraded}
              />
            </div>
          )}

          {/* Breakdown by condition */}
          {Object.keys(portfolioValue.breakdown).length > 0 && (
            <div className="space-y-2">
              <h2 className="text-sm font-semibold text-slate-700">By Condition</h2>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
                {Object.entries(portfolioValue.breakdown).map(([condition, data]) => (
                  <div key={condition} className="bg-white rounded-2xl border border-slate-200 p-4">
                    <div className="text-xs text-slate-400 font-medium mb-1">{condition}</div>
                    <div className="text-xl font-bold text-slate-800">
                      {fmt(parseFloat(data.value as any))}
                    </div>
                    <div className="text-xs text-slate-400 mt-0.5">
                      {data.count} cards · {parseFloat(data.percentage as any).toFixed(1)}%
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {activeView === "history" && history && (
        <HistoricalChart history={history} />
      )}

      {activeView === "sales" && (
        <SalesHistory
          summary={salesSummary}
          onToast={onToast}
          onOpenDetails={onOpenDetails}
          onSaleDeleted={fetchPortfolioData}
        />
      )}

      {activeView === "prices" && (
        <MarketPriceManager userId={userId} onToast={onToast} />
      )}

      {activeView === "record-sale" && (
        <SaleRecorder userId={userId} onToast={onToast} onSaleRecorded={fetchPortfolioData} />
      )}

      {editingItem && (
        <EditInventoryModal
          item={editingItem}
          onClose={() => setEditingItem(null)}
          onSave={saveItemEdits}
        />
      )}

      {saleItem && (
        <QuickSaleModal
          item={saleItem.item}
          mode={saleItem.mode}
          onClose={() => setSaleItem(null)}
          onConfirm={handleSaleConfirm}
        />
      )}
    </div>
  );
}
