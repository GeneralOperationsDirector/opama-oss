import React, { useEffect, useState } from "react";
import { motion } from "motion/react";
import {
  TrendingUp, TrendingDown, Minus, ExternalLink, Loader2, RefreshCw,
} from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from "recharts";
import { api } from "../../lib/api";
import type { PortfolioValue } from "../../types";
import type { AppModule } from "../../types";
import { TEMPLATES } from "../collections/templates";

/* ─── Types ──────────────────────────────────────────────────────── */
interface CollectionsSummary {
  total_assets: number;
  total_cost: number;
  total_estimated_value: number;
  unrealized_gain: number;
  categories: { category: string; count: number; value: number }[];
}

interface PortfolioData {
  pokemon: PortfolioValue | null;
  collections: CollectionsSummary | null;
}

/* ─── Helpers ────────────────────────────────────────────────────── */
function fmt(n: number, compact = false) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: compact ? 0 : 2,
    notation: compact && Math.abs(n) >= 10_000 ? "compact" : "standard",
  }).format(n);
}

function pct(part: number, total: number) {
  if (!total) return 0;
  return Math.round((part / total) * 100);
}

function gainColor(n: number) {
  return n > 0 ? "text-emerald-600" : n < 0 ? "text-red-500" : "text-slate-500";
}

function gainBg(n: number) {
  return n > 0 ? "bg-emerald-50 border-emerald-200" : n < 0 ? "bg-red-50 border-red-200" : "bg-slate-50 border-slate-200";
}

function GainIcon({ n }: { n: number }) {
  if (n > 0) return <TrendingUp className="w-4 h-4" />;
  if (n < 0) return <TrendingDown className="w-4 h-4" />;
  return <Minus className="w-4 h-4" />;
}

const BAR_COLORS = [
  "#f97316", // orange – Pokémon TCG
  "#6366f1", // indigo
  "#8b5cf6", // violet
  "#06b6d4", // cyan
  "#10b981", // emerald
  "#f59e0b", // amber
  "#ec4899", // pink
  "#3b82f6", // blue
];

interface ChartEntry { name: string; value: number; colorIndex: number }

function AllocationChart({ data }: { data: ChartEntry[] }) {
  if (data.length === 0) return null;
  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-5">
      <h2 className="text-sm font-semibold text-slate-700 mb-4">Value by Asset Class</h2>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }} barCategoryGap="30%">
          <CartesianGrid vertical={false} stroke="#f1f5f9" />
          <XAxis
            dataKey="name"
            tick={{ fontSize: 11, fill: "#94a3b8" }}
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
            {data.map((entry) => (
              <Cell key={entry.name} fill={BAR_COLORS[entry.colorIndex % BAR_COLORS.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// Find emoji for a category from the template library
function emojiForCategory(cat: string): string {
  const match = TEMPLATES.find(
    (t) => t.category.toLowerCase() === cat.toLowerCase() ||
           t.name.toLowerCase() === cat.toLowerCase()
  );
  return match?.emoji ?? "📦";
}

/* ─── Sub-components ─────────────────────────────────────────────── */
function StatCard({ label, value, sub, color = "text-slate-800" }: {
  label: string; value: string; sub?: string; color?: string;
}) {
  return (
    <div className="bg-white rounded-2xl border border-slate-200 p-4">
      <div className="text-xs text-slate-400 font-medium mb-1">{label}</div>
      <div className={`text-2xl font-bold ${color}`}>{value}</div>
      {sub && <div className="text-xs text-slate-500 mt-0.5">{sub}</div>}
    </div>
  );
}

function AllocationBar({ label, emoji, value, total, color, onDrillIn }: {
  label: string; emoji: string; value: number; total: number;
  color: string; onDrillIn?: () => void;
}) {
  const p = pct(value, total);
  return (
    <button
      onClick={onDrillIn}
      disabled={!onDrillIn}
      className="w-full text-left group flex items-center gap-3 py-2.5 px-1 rounded-lg hover:bg-slate-50 transition-colors disabled:cursor-default"
    >
      <span className="text-xl flex-shrink-0 w-7 text-center">{emoji}</span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-1">
          <span className="text-sm font-medium text-slate-700 truncate">{label}</span>
          <span className="text-sm font-semibold text-slate-800 ml-2 flex-shrink-0">{fmt(value, true)}</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${p}%` }}
              transition={{ duration: 0.6, ease: "easeOut" }}
              className={`h-full rounded-full ${color}`}
            />
          </div>
          <span className="text-xs text-slate-400 w-8 text-right flex-shrink-0">{p}%</span>
        </div>
      </div>
      {onDrillIn && (
        <ExternalLink className="w-3.5 h-3.5 text-slate-300 group-hover:text-indigo-500 flex-shrink-0 transition-colors" />
      )}
    </button>
  );
}

/* ─── Main component ─────────────────────────────────────────────── */
export default function MainPortfolioView({
  userId,
  onNavigate,
}: {
  userId: number;
  onNavigate: (module: AppModule, tab?: string) => void;
}) {
  const [data, setData] = useState<PortfolioData>({ pokemon: null, collections: null });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [pokRes, colRes] = await Promise.allSettled([
        api<PortfolioValue>(`/portfolio/value?user_id=${userId}`),
        api<CollectionsSummary>(`/assets/summary?user_id=${userId}`),
      ]);
      setData({
        pokemon: pokRes.status === "fulfilled" ? pokRes.value : null,
        collections: colRes.status === "fulfilled" ? colRes.value : null,
      });
    } catch (e) {
      setError("Failed to load portfolio data.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [userId]);

  /* Derived totals — parseFloat guards against Decimal strings from the backend */
  const pokValue  = parseFloat(data.pokemon?.total_value as any) || 0;
  const pokCost   = parseFloat(data.pokemon?.total_cost as any) || 0;
  const colValue  = parseFloat(data.collections?.total_estimated_value as any) || 0;
  const colCost   = parseFloat(data.collections?.total_cost as any) || 0;
  const totalValue = pokValue + colValue;
  const totalCost  = pokCost + colCost;
  const totalGain  = totalValue - totalCost;
  const gainPct    = totalCost > 0 ? ((totalGain / totalCost) * 100).toFixed(1) : null;

  /* Sort collection categories by value desc */
  const collectionCategories = [...(data.collections?.categories ?? [])]
    .sort((a, b) => b.value - a.value);

  /* Chart data: Pokémon TCG first, then each collection category */
  const chartData: ChartEntry[] = [
    ...(pokValue > 0 ? [{ name: "Pokémon TCG", value: pokValue, colorIndex: 0 }] : []),
    ...collectionCategories.map((cat, i) => ({
      name: cat.category.length > 10 ? cat.category.slice(0, 9) + "…" : cat.category,
      value: parseFloat(cat.value as any) || 0,
      colorIndex: i + 1,
    })),
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24 gap-2 text-slate-400">
        <Loader2 className="w-5 h-5 animate-spin" />
        <span className="text-sm">Loading portfolio…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="py-16 text-center space-y-3">
        <div className="text-3xl">⚠️</div>
        <p className="text-slate-600">{error}</p>
        <button onClick={load} className="inline-flex items-center gap-1.5 text-sm text-indigo-600 hover:underline">
          <RefreshCw className="w-3.5 h-3.5" /> Retry
        </button>
      </div>
    );
  }

  const hasAnyData = totalValue > 0 || totalCost > 0;

  return (
    <div className="space-y-8 max-w-4xl mx-auto">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Portfolio</h1>
          <p className="text-sm text-slate-500 mt-0.5">Combined value across all your modules</p>
        </div>
        <button
          onClick={load}
          className="w-8 h-8 rounded-lg flex items-center justify-center text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
          title="Refresh"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {!hasAnyData ? (
        <div className="py-20 text-center space-y-3">
          <div className="text-4xl">📊</div>
          <div className="text-slate-600 font-medium">No portfolio data yet</div>
          <div className="text-sm text-slate-400">
            Add inventory to Pokémon TCG or items to Collections to see your portfolio here.
          </div>
        </div>
      ) : (
        <>
          {/* ── Summary stats ── */}
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            className="grid grid-cols-2 lg:grid-cols-4 gap-3"
          >
            <StatCard label="Total Value" value={fmt(totalValue, true)} />
            <StatCard label="Total Cost" value={fmt(totalCost, true)} />
            <div className={`rounded-2xl border p-4 ${gainBg(totalGain)}`}>
              <div className="text-xs text-slate-400 font-medium mb-1">Unrealized Gain</div>
              <div className={`text-2xl font-bold flex items-center gap-1.5 ${gainColor(totalGain)}`}>
                <GainIcon n={totalGain} />
                {fmt(Math.abs(totalGain), true)}
              </div>
              {gainPct && (
                <div className={`text-xs mt-0.5 ${gainColor(totalGain)}`}>
                  {totalGain >= 0 ? "+" : ""}{gainPct}%
                </div>
              )}
            </div>
            <StatCard
              label="Total Items"
              value={String(
                (data.pokemon?.total_items ?? 0) + (data.collections?.total_assets ?? 0)
              )}
              sub={[
                data.pokemon?.total_items ? `${data.pokemon.total_items} TCG cards` : null,
                data.collections?.total_assets ? `${data.collections.total_assets} collection items` : null,
              ].filter(Boolean).join(" · ")}
            />
          </motion.div>

          {/* ── Bar chart ── */}
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.08 }}
          >
            <AllocationChart data={chartData} />
          </motion.div>

          {/* ── Module allocation ── */}
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="bg-white rounded-2xl border border-slate-200 p-5"
          >
            <h2 className="text-sm font-semibold text-slate-700 mb-4">Allocation by Module</h2>
            <div className="space-y-1 divide-y divide-slate-50">
              {pokValue > 0 && (
                <AllocationBar
                  label="Pokémon TCG"
                  emoji="⚡"
                  value={pokValue}
                  total={totalValue}
                  color="bg-orange-400"
                  onDrillIn={() => onNavigate("pokemon", "portfolio")}
                />
              )}
              {colValue > 0 && (
                <AllocationBar
                  label="Collections"
                  emoji="📦"
                  value={colValue}
                  total={totalValue}
                  color="bg-indigo-500"
                  onDrillIn={() => onNavigate("custom")}
                />
              )}
            </div>
          </motion.div>

          {/* ── Collections breakdown ── */}
          {collectionCategories.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="bg-white rounded-2xl border border-slate-200 p-5"
            >
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-semibold text-slate-700">Collections Breakdown</h2>
                <button
                  onClick={() => onNavigate("custom")}
                  className="text-xs text-indigo-600 hover:text-indigo-800 font-medium"
                >
                  Manage →
                </button>
              </div>
              <div className="space-y-1 divide-y divide-slate-50">
                {collectionCategories.map((cat) => (
                  <AllocationBar
                    key={cat.category}
                    label={`${cat.category}  ·  ${cat.count} item${cat.count !== 1 ? "s" : ""}`}
                    emoji={emojiForCategory(cat.category)}
                    value={parseFloat(cat.value as any) || 0}
                    total={colValue}
                    color="bg-violet-400"
                    onDrillIn={() => {
                      window.dispatchEvent(
                        new CustomEvent("filterCollectionCategory", { detail: cat.category })
                      );
                      onNavigate("custom");
                    }}
                  />
                ))}
              </div>
            </motion.div>
          )}

          {/* ── Pokémon TCG detail link ── */}
          {pokValue > 0 && (
            <motion.button
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.3 }}
              onClick={() => onNavigate("pokemon", "portfolio")}
              className="w-full rounded-2xl border border-slate-200 bg-white p-5 flex items-center justify-between hover:shadow-md hover:-translate-y-0.5 transition-all group"
            >
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-yellow-400 to-orange-500 flex items-center justify-center text-xl">
                  ⚡
                </div>
                <div className="text-left">
                  <div className="font-semibold text-slate-800">Pokémon TCG Portfolio</div>
                  <div className="text-sm text-slate-500">
                    Price history, top holdings, sales tracking
                  </div>
                </div>
              </div>
              <ExternalLink className="w-4 h-4 text-slate-300 group-hover:text-indigo-500 transition-colors" />
            </motion.button>
          )}
        </>
      )}
    </div>
  );
}
