/**
 * RealEstateModule — Property Records.
 *
 * Three tabs: Mortgages (loan terms and balances), Valuations (appraisal /
 * market estimate / tax assessment history), and Property Tax (annual tax
 * records with due dates). Backend: services/real_estate. Every record
 * links to a CustomAsset in the "Real Estate" category — the asset pickers
 * in each tab are pre-filtered to that category. Properties themselves are
 * added/removed from Collections (onNavigate jumps there with the right
 * template).
 */
import React, { useCallback, useEffect, useState } from "react";
import { Landmark, TrendingUp, Receipt, Plus } from "lucide-react";
import { api } from "../../lib/api";
import type { AppModule } from "../../types";
import type { CustomAsset } from "../custom-assets/types";
import type { RealEstateSummary } from "./types";
import MortgagesTab from "./MortgagesTab";
import ValuationsTab from "./ValuationsTab";
import PropertyTaxTab from "./PropertyTaxTab";

interface Props {
  userId: number;
  onToast: (msg: string, type?: "success" | "error" | "info") => void;
  onNavigate: (module: AppModule, tab?: string, templateId?: string) => void;
}

type Tab = "mortgages" | "valuations" | "tax";

function fmtUSD(n: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD", maximumFractionDigits: 0,
  }).format(n);
}

export default function RealEstateModule({ onToast, onNavigate }: Props) {
  const [tab, setTab] = useState<Tab>("mortgages");
  const [summary, setSummary] = useState<RealEstateSummary | null>(null);
  const [assets, setAssets] = useState<CustomAsset[]>([]);

  const loadSummary = useCallback(async () => {
    try {
      const s = await api<RealEstateSummary>("/real-estate/summary");
      setSummary(s);
    } catch {
      onToast("Failed to load property summary", "error");
    }
  }, [onToast]);

  useEffect(() => {
    loadSummary();
    api<CustomAsset[]>("/assets").then(setAssets).catch(() => setAssets([]));
  }, [loadSummary]);

  const propertyAssets = assets.filter((a) => a.category.toLowerCase() === "real estate");

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
            🏠 Property Records
          </h2>
          <p className="text-sm text-slate-500 mt-0.5">
            Track mortgage details, valuation history, and property tax records for your real estate.
          </p>
        </div>
        <button
          onClick={() => onNavigate("custom", undefined, "real-estate")}
          className="flex items-center gap-1.5 px-3 py-1.5 border border-slate-200 rounded-lg text-xs font-medium text-slate-600 hover:bg-slate-50"
        >
          <Plus className="w-3.5 h-3.5" />🏠 Add Property
        </button>
      </div>

      {/* Summary strip */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          <div className="bg-white border border-slate-200 rounded-xl p-3">
            <div className="text-xs text-slate-400 uppercase tracking-wide">Properties</div>
            <div className="text-lg font-semibold text-slate-800">{summary.property_count}</div>
          </div>
          <div className="bg-white border border-slate-200 rounded-xl p-3">
            <div className="text-xs text-slate-400 uppercase tracking-wide">Mortgage Balance</div>
            <div className="text-lg font-semibold text-slate-800">{fmtUSD(summary.total_mortgage_balance)}</div>
          </div>
          <div className="bg-white border border-slate-200 rounded-xl p-3">
            <div className="text-xs text-slate-400 uppercase tracking-wide">Est. Value</div>
            <div className="text-lg font-semibold text-slate-800">{fmtUSD(summary.total_valuation)}</div>
          </div>
          <div className="bg-white border border-slate-200 rounded-xl p-3">
            <div className="text-xs text-slate-400 uppercase tracking-wide">Est. Equity</div>
            <div className="text-lg font-semibold text-slate-800">{fmtUSD(summary.estimated_equity)}</div>
          </div>
          <div className="bg-white border border-slate-200 rounded-xl p-3">
            <div className="text-xs text-slate-400 uppercase tracking-wide">Taxes Due (60d)</div>
            <div className={`text-lg font-semibold ${summary.taxes_due_soon > 0 ? "text-amber-600" : "text-slate-800"}`}>
              {summary.taxes_due_soon}
            </div>
          </div>
        </div>
      )}

      {/* Tab strip */}
      <div className="flex gap-1 border-b border-slate-200">
        <button
          onClick={() => setTab("mortgages")}
          className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
            tab === "mortgages"
              ? "border-indigo-600 text-indigo-600"
              : "border-transparent text-slate-500 hover:text-slate-800 hover:border-slate-300"
          }`}
        >
          <Landmark className="w-4 h-4" /> Mortgages
        </button>
        <button
          onClick={() => setTab("valuations")}
          className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
            tab === "valuations"
              ? "border-indigo-600 text-indigo-600"
              : "border-transparent text-slate-500 hover:text-slate-800 hover:border-slate-300"
          }`}
        >
          <TrendingUp className="w-4 h-4" /> Valuations
        </button>
        <button
          onClick={() => setTab("tax")}
          className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
            tab === "tax"
              ? "border-indigo-600 text-indigo-600"
              : "border-transparent text-slate-500 hover:text-slate-800 hover:border-slate-300"
          }`}
        >
          <Receipt className="w-4 h-4" /> Property Tax
        </button>
      </div>

      {/* Tab content */}
      <div>
        {tab === "mortgages" ? (
          <MortgagesTab assets={propertyAssets} onToast={onToast} onSummaryChange={loadSummary} />
        ) : tab === "valuations" ? (
          <ValuationsTab assets={propertyAssets} onToast={onToast} onSummaryChange={loadSummary} />
        ) : (
          <PropertyTaxTab assets={propertyAssets} onToast={onToast} onSummaryChange={loadSummary} />
        )}
      </div>
    </div>
  );
}
