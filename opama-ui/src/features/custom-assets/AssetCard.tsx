import React from "react";
import { Pencil, Trash2, TrendingUp, TrendingDown, Minus } from "lucide-react";
import { API_BASE } from "../../lib/api";
import type { CustomAsset } from "./types";

function fmt(n: number | null | undefined) {
  if (n == null) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(n);
}

interface Props {
  asset: CustomAsset;
  onEdit: () => void;
  onDelete: () => void;
  onOpen: () => void;
}

export default function AssetCard({ asset, onEdit, onDelete, onOpen }: Props) {
  const gain =
    asset.estimated_value != null && asset.purchase_price != null
      ? (asset.estimated_value - asset.purchase_price) * asset.quantity
      : null;

  const GainIcon =
    gain == null ? null : gain > 0 ? TrendingUp : gain < 0 ? TrendingDown : Minus;
  const gainColor =
    gain == null ? "" : gain > 0 ? "text-emerald-600" : gain < 0 ? "text-red-500" : "text-slate-500";

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4 hover:shadow-md transition-shadow flex flex-col gap-3">
      {/* Image or placeholder — portrait 2:3 ratio */}
      <button onClick={onOpen} className="w-full text-left">
        {asset.image_url ? (
          <div className="w-full aspect-[2/3] rounded-lg overflow-hidden bg-slate-100">
            <img
              src={(() => {
                const src = asset.image_thumb_url || asset.image_url;
                return src.startsWith("/") ? `${API_BASE}${src}` : src;
              })()}
              alt={asset.name}
              className="w-full h-full object-cover"
            />
          </div>
        ) : (
          <div className="w-full aspect-[2/3] rounded-lg bg-gradient-to-br from-slate-100 to-slate-200 flex items-center justify-center text-4xl select-none">
            📦
          </div>
        )}
      </button>

      {/* Info */}
      <div className="space-y-1">
        <button onClick={onOpen} className="text-left w-full">
          <div className="font-semibold text-slate-800 text-sm leading-tight">{asset.name}</div>
        </button>
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded-full">
            {asset.category}
          </span>
          {asset.condition && (
            <span className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">
              {asset.condition}
            </span>
          )}
          {asset.quantity > 1 && (
            <span className="text-xs text-slate-400">×{asset.quantity}</span>
          )}
        </div>
      </div>

      {/* Valuation */}
      <div className="grid grid-cols-2 gap-1 text-xs">
        <div>
          <div className="text-slate-400">Cost</div>
          <div className="font-medium">{fmt(asset.purchase_price != null ? asset.purchase_price * asset.quantity : null)}</div>
        </div>
        <div>
          <div className="text-slate-400">Est. Value</div>
          <div className="font-medium">{fmt(asset.estimated_value != null ? asset.estimated_value * asset.quantity : null)}</div>
        </div>
        {gain != null && GainIcon && (
          <div className={`col-span-2 flex items-center gap-1 ${gainColor}`}>
            <GainIcon className="w-3 h-3" />
            <span className="font-medium">{fmt(gain)}</span>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex gap-2 pt-1 border-t border-slate-100">
        <button
          onClick={onEdit}
          className="flex-1 flex items-center justify-center gap-1 text-xs text-slate-600 hover:text-indigo-600 py-1"
        >
          <Pencil className="w-3 h-3" /> Edit
        </button>
        <button
          onClick={onDelete}
          className="flex-1 flex items-center justify-center gap-1 text-xs text-slate-600 hover:text-red-500 py-1"
        >
          <Trash2 className="w-3 h-3" /> Delete
        </button>
      </div>
    </div>
  );
}
