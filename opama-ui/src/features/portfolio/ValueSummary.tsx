import React from "react";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import type { PortfolioValue, RealizedGainsSummary } from "../../types";

function fmt(n: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(n);
}

function gainColor(n: number) {
  return n > 0 ? "text-emerald-600" : n < 0 ? "text-red-500" : "text-slate-500";
}

function GainIcon({ n }: { n: number }) {
  if (n > 0) return <TrendingUp className="w-4 h-4" />;
  if (n < 0) return <TrendingDown className="w-4 h-4" />;
  return <Minus className="w-4 h-4" />;
}

interface ValueSummaryProps {
  portfolioValue: PortfolioValue;
  salesSummary: RealizedGainsSummary | null;
}

export default function ValueSummary({ portfolioValue, salesSummary }: ValueSummaryProps) {
  const unrealizedGain = parseFloat(portfolioValue.unrealized_gain as any) || 0;
  const unrealizedPct  = parseFloat(portfolioValue.unrealized_gain_pct as any) || 0;
  const realizedGain   = salesSummary ? parseFloat(salesSummary.total_realized_gain as any) || 0 : null;
  const realizedPct    = salesSummary ? parseFloat(salesSummary.total_realized_gain_pct as any) || 0 : 0;

  const stats = [
    {
      label: "Portfolio Value",
      value: fmt(parseFloat(portfolioValue.total_value as any)),
      sub: `${portfolioValue.total_items} items · ${portfolioValue.unique_cards} unique`,
      color: "text-slate-800",
    },
    {
      label: "Cost Basis",
      value: fmt(parseFloat(portfolioValue.total_cost as any)),
      sub: "Original purchase prices",
      color: "text-slate-800",
    },
    {
      label: "Unrealized Gain",
      value: `${unrealizedGain >= 0 ? "+" : ""}${fmt(unrealizedGain)}`,
      sub: `${unrealizedGain >= 0 ? "+" : ""}${unrealizedPct.toFixed(2)}% on holdings`,
      color: gainColor(unrealizedGain),
      icon: <GainIcon n={unrealizedGain} />,
    },
    ...(realizedGain !== null ? [{
      label: "Realized Gains",
      value: `${realizedGain >= 0 ? "+" : ""}${fmt(realizedGain)}`,
      sub: `${realizedPct.toFixed(2)}% · ${salesSummary!.total_sales} sales`,
      color: gainColor(realizedGain),
      icon: <GainIcon n={realizedGain} />,
    }] : []),
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {stats.map((s) => (
        <div key={s.label} className="bg-white rounded-2xl border border-slate-200 p-4">
          <div className="text-xs text-slate-400 font-medium mb-1">{s.label}</div>
          <div className={`text-2xl font-bold flex items-center gap-1.5 ${s.color}`}>
            {s.icon}
            {s.value}
          </div>
          {s.sub && <div className="text-xs text-slate-500 mt-0.5">{s.sub}</div>}
        </div>
      ))}

      {portfolioValue.graded_count > 0 && (
        <div className="bg-white rounded-2xl border border-violet-200 p-4 col-span-2">
          <div className="text-xs text-violet-500 font-medium mb-1">Graded Cards</div>
          <div className="text-2xl font-bold text-violet-700">
            {fmt(parseFloat(portfolioValue.graded_value as any))}
          </div>
          <div className="text-xs text-slate-500 mt-0.5">
            {portfolioValue.graded_count} graded ·{" "}
            {((parseFloat(portfolioValue.graded_value as any) / parseFloat(portfolioValue.total_value as any)) * 100).toFixed(1)}% of portfolio
          </div>
        </div>
      )}
    </div>
  );
}
