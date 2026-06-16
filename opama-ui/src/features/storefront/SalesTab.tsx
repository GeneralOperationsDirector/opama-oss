import React from "react";
import { DollarSign, ShoppingBag, TrendingUp } from "lucide-react";
import { API_BASE } from "../../lib/api";
import type { SalesData } from "./types";

interface Props {
  data: SalesData | null;
}

function fmtCAD(n: number) {
  return new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD" }).format(n);
}

export default function SalesTab({ data }: Props) {
  if (!data || data.total_sold === 0) {
    return (
      <div className="py-20 text-center text-slate-400 space-y-2">
        <div className="text-4xl">💰</div>
        <div className="font-medium text-slate-600">No sales yet</div>
        <p className="text-sm">Sold items will appear here once a purchase is recorded.</p>
      </div>
    );
  }

  const platforms = Object.entries(data.by_platform).sort((a, b) => b[1] - a[1]);

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      <div className="grid sm:grid-cols-3 gap-3">
        {[
          { icon: <DollarSign className="w-4 h-4" />, label: "Total Revenue", value: fmtCAD(data.total_revenue_cad), color: "text-emerald-600" },
          { icon: <ShoppingBag className="w-4 h-4" />, label: "Items Sold", value: String(data.total_sold), color: "text-indigo-600" },
          { icon: <TrendingUp className="w-4 h-4" />, label: "Avg Sale", value: data.total_sold ? fmtCAD(data.total_revenue_cad / data.total_sold) : "—", color: "text-slate-700" },
        ].map(s => (
          <div key={s.label} className="bg-white border border-slate-200 rounded-xl p-4 flex items-center gap-3">
            <div className={s.color}>{s.icon}</div>
            <div>
              <div className="text-xs text-slate-400">{s.label}</div>
              <div className={`font-semibold text-sm ${s.color}`}>{s.value}</div>
            </div>
          </div>
        ))}
      </div>

      {/* By platform */}
      {platforms.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-2">
          <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">By Platform</div>
          {platforms.map(([plat, rev]) => (
            <div key={plat} className="flex items-center justify-between text-sm">
              <span className="capitalize text-slate-700">{plat}</span>
              <span className="font-medium text-emerald-600">{fmtCAD(rev)}</span>
            </div>
          ))}
        </div>
      )}

      {/* Sale items */}
      <div className="space-y-3">
        <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Sold Items</div>
        {data.items.map(item => {
          const thumb = item.image_thumb_url || item.image_url;
          const imgSrc = thumb ? (thumb.startsWith("/") ? `${API_BASE}${thumb}` : thumb) : null;
          return (
            <div key={item.id} className="bg-white border border-slate-200 rounded-xl p-4 flex gap-3 items-start">
              {imgSrc ? (
                <img src={imgSrc} alt={item.name} className="w-12 h-16 object-cover rounded-lg bg-slate-100 flex-shrink-0" />
              ) : (
                <div className="w-12 h-16 rounded-lg bg-slate-100 flex-shrink-0" />
              )}
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-slate-800 text-sm">{item.name}</div>
                <div className="text-xs text-slate-400 mt-0.5">{item.category}{item.condition ? ` · ${item.condition}` : ""}</div>
                <div className="mt-2 flex gap-4 text-xs text-slate-600">
                  <span><span className="text-slate-400">Sold: </span>{item.sale_date}</span>
                  <span><span className="text-slate-400">Price: </span>
                    <span className="text-emerald-600 font-medium">{item.sale_price_cad != null ? fmtCAD(item.sale_price_cad) : "—"}</span>
                  </span>
                  {item.sale_platform && <span><span className="text-slate-400">via </span>{item.sale_platform}</span>}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
