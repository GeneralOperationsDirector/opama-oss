import React from "react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { PortfolioHistory } from "../../types";

function fmt(n: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);
}

interface HistoricalChartProps {
  history: PortfolioHistory;
}

export default function HistoricalChart({ history }: HistoricalChartProps) {
  if (!history.snapshots || history.snapshots.length === 0) {
    return (
      <div className="bg-white rounded-2xl border border-slate-200 p-8 text-center">
        <div className="text-slate-400 font-medium mb-1">No historical data yet</div>
        <p className="text-sm text-slate-400">
          Create snapshots to track your portfolio value over time.
        </p>
      </div>
    );
  }

  const { summary } = history;
  const change = parseFloat(summary.absolute_change as any);
  const isUp = change >= 0;
  const color = isUp ? "#10b981" : "#ef4444";

  const data = history.snapshots.map((s) => ({
    date: new Date(s.date).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
    value: parseFloat(s.total_value as any),
  }));

  const summaryStats = [
    { label: "Start", value: fmt(parseFloat(summary.start_value as any)) },
    { label: "Current", value: fmt(parseFloat(summary.end_value as any)) },
    {
      label: "Change",
      value: `${isUp ? "+" : ""}${fmt(change)}`,
      sub: `${isUp ? "+" : ""}${parseFloat(summary.percentage_change as any).toFixed(2)}%`,
      color: isUp ? "text-emerald-600" : "text-red-500",
    },
    { label: "Peak", value: fmt(parseFloat(summary.peak_value as any)) },
  ];

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {summaryStats.map((s) => (
          <div key={s.label} className="bg-white rounded-2xl border border-slate-200 p-4">
            <div className="text-xs text-slate-400 font-medium mb-1">{s.label}</div>
            <div className={`text-lg font-bold ${s.color ?? "text-slate-800"}`}>{s.value}</div>
            {s.sub && <div className={`text-xs mt-0.5 ${s.color ?? "text-slate-500"}`}>{s.sub}</div>}
          </div>
        ))}
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 p-5">
        <ResponsiveContainer width="100%" height={220}>
          <AreaChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="tcgAreaGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={color} stopOpacity={0.15} />
                <stop offset="95%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid vertical={false} stroke="#f1f5f9" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11, fill: "#94a3b8" }}
              axisLine={false}
              tickLine={false}
              interval="preserveStartEnd"
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
              contentStyle={{ border: "1px solid #e2e8f0", borderRadius: 10, fontSize: 12 }}
              cursor={{ stroke: "#cbd5e1", strokeWidth: 1 }}
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke={color}
              strokeWidth={2.5}
              fill="url(#tcgAreaGrad)"
              dot={false}
              activeDot={{ r: 4, fill: color }}
            />
          </AreaChart>
        </ResponsiveContainer>
        <div className="flex justify-between mt-2 text-xs text-slate-400">
          <span>{new Date(history.period.start_date).toLocaleDateString()}</span>
          <span>{history.period.days} days</span>
          <span>{new Date(history.period.end_date).toLocaleDateString()}</span>
        </div>
      </div>
    </div>
  );
}
