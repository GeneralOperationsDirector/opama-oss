import React from "react";
import { Edit, DollarSign, Repeat, TrendingUp, TrendingDown } from "lucide-react";
import CardTile from "../../shared/CardTile";
import type { CardValuation } from "../../types";

function fmt(n: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(n);
}

interface TopHoldingsProps {
  holdings: CardValuation[];
  onOpenDetails?: (cardId: string) => void;
  onEditValue?: (cardId: string, condition: string, cardName: string) => void;
  onSold?: (cardId: string, condition: string, cardName: string) => void;
  onTraded?: (cardId: string, condition: string, cardName: string) => void;
}

export default function TopHoldings({ holdings, onOpenDetails, onEditValue, onSold, onTraded }: TopHoldingsProps) {
  return (
    <div className="space-y-2">
      {holdings.map((holding, index) => {
        const gain = parseFloat(holding.unrealized_gain as any);
        const gainPct = parseFloat(holding.unrealized_gain_pct as any) || 0;
        const hasGain = holding.unrealized_gain !== null && holding.unrealized_gain !== undefined;
        const isUp = gain >= 0;

        return (
          <div
            key={holding.card_id}
            className="flex items-center gap-4 bg-white rounded-2xl border border-slate-200 p-4 hover:shadow-sm transition-shadow"
          >
            {/* Rank */}
            <div className="flex-shrink-0 w-7 h-7 rounded-full bg-slate-100 flex items-center justify-center font-bold text-xs text-slate-500">
              {index + 1}
            </div>

            {/* Card thumbnail */}
            <div className="flex-shrink-0">
              <CardTile
                cardLike={{ id: holding.card_id, name: holding.card_name, set_id: holding.set_id }}
                onOpenDetails={onOpenDetails}
                fallbackId={holding.card_id}
              />
            </div>

            {/* Info */}
            <div className="flex-1 min-w-0">
              <div className="font-semibold text-slate-800 truncate">{holding.card_name}</div>
              <div className="text-xs text-slate-400 mt-0.5">
                {holding.set_name} · {holding.condition} · ×{holding.quantity}
              </div>
              {holding.price_source && (
                <div className="text-xs text-slate-300 mt-0.5">
                  {holding.price_source}
                  {holding.confidence_score ? ` · ${holding.confidence_score}% confidence` : ""}
                </div>
              )}
            </div>

            {/* Value */}
            <div className="flex-shrink-0 text-right space-y-0.5 min-w-[80px]">
              <div className="text-lg font-bold text-slate-800">{fmt(parseFloat(holding.total_value as any))}</div>
              <div className="text-xs text-slate-400">{fmt(parseFloat(holding.unit_price as any))} each</div>
              {hasGain && (
                <div className={`text-xs font-medium flex items-center justify-end gap-0.5 ${isUp ? "text-emerald-600" : "text-red-500"}`}>
                  {isUp ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                  {isUp ? "+" : ""}{fmt(gain)} ({isUp ? "+" : ""}{gainPct.toFixed(1)}%)
                </div>
              )}
              {holding.price_change_30d != null && (
                <div className={`text-xs ${parseFloat(holding.price_change_30d as any) >= 0 ? "text-sky-500" : "text-orange-400"}`}>
                  30d: {parseFloat(holding.price_change_30d as any) >= 0 ? "+" : ""}{parseFloat(holding.price_change_30d as any).toFixed(1)}%
                </div>
              )}
            </div>

            {/* Actions */}
            <div className="flex-shrink-0 flex flex-col gap-1">
              {onEditValue && (
                <button
                  onClick={() => onEditValue(holding.card_id, holding.condition, holding.card_name)}
                  className="flex items-center gap-1 px-2 py-1 rounded-lg text-xs text-slate-500 hover:bg-slate-100 transition-colors"
                >
                  <Edit className="w-3 h-3" /> Value
                </button>
              )}
              {onSold && (
                <button
                  onClick={() => onSold(holding.card_id, holding.condition, holding.card_name)}
                  className="flex items-center gap-1 px-2 py-1 rounded-lg text-xs text-emerald-600 hover:bg-emerald-50 transition-colors"
                >
                  <DollarSign className="w-3 h-3" /> Sold
                </button>
              )}
              {onTraded && (
                <button
                  onClick={() => onTraded(holding.card_id, holding.condition, holding.card_name)}
                  className="flex items-center gap-1 px-2 py-1 rounded-lg text-xs text-violet-600 hover:bg-violet-50 transition-colors"
                >
                  <Repeat className="w-3 h-3" /> Traded
                </button>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
