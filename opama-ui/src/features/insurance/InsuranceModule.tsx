/**
 * InsuranceModule — Insurance & Appraisals.
 *
 * Two tabs: Policies (coverage, premiums, renewal dates, and itemized
 * scheduled coverage linked to collection assets) and Appraisals (standalone
 * or asset-linked valuation records). Backend: services/insurance.
 */
import React, { useCallback, useEffect, useState } from "react";
import { ShieldCheck, FileSearch } from "lucide-react";
import { api } from "../../lib/api";
import type { CustomAsset } from "../custom-assets/types";
import type { InsuranceSummary } from "./types";
import PoliciesTab from "./PoliciesTab";
import AppraisalsTab from "./AppraisalsTab";

interface Props {
  userId: number;
  onToast: (msg: string, type?: "success" | "error" | "info") => void;
}

type Tab = "policies" | "appraisals";

function fmtUSD(n: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD", maximumFractionDigits: 0,
  }).format(n);
}

export default function InsuranceModule({ onToast }: Props) {
  const [tab, setTab] = useState<Tab>("policies");
  const [summary, setSummary] = useState<InsuranceSummary | null>(null);
  const [assets, setAssets] = useState<CustomAsset[]>([]);

  const loadSummary = useCallback(async () => {
    try {
      const s = await api<InsuranceSummary>("/insurance/summary");
      setSummary(s);
    } catch {
      onToast("Failed to load insurance summary", "error");
    }
  }, [onToast]);

  useEffect(() => {
    loadSummary();
    api<CustomAsset[]>("/assets").then(setAssets).catch(() => setAssets([]));
  }, [loadSummary]);

  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
          🛡️ Insurance &amp; Appraisals
        </h2>
        <p className="text-sm text-slate-500 mt-0.5">
          Track policy coverage, scheduled items, and appraisal records for your collection.
        </p>
      </div>

      {/* Summary strip */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="bg-white border border-slate-200 rounded-xl p-3">
            <div className="text-xs text-slate-400 uppercase tracking-wide">Policies</div>
            <div className="text-lg font-semibold text-slate-800">{summary.policy_count}</div>
          </div>
          <div className="bg-white border border-slate-200 rounded-xl p-3">
            <div className="text-xs text-slate-400 uppercase tracking-wide">Total Coverage</div>
            <div className="text-lg font-semibold text-slate-800">{fmtUSD(summary.total_coverage)}</div>
          </div>
          <div className="bg-white border border-slate-200 rounded-xl p-3">
            <div className="text-xs text-slate-400 uppercase tracking-wide">Appraisals</div>
            <div className="text-lg font-semibold text-slate-800">{summary.appraisal_count}</div>
          </div>
          <div className="bg-white border border-slate-200 rounded-xl p-3">
            <div className="text-xs text-slate-400 uppercase tracking-wide">Renewals (60d)</div>
            <div className={`text-lg font-semibold ${summary.policies_expiring_soon > 0 ? "text-amber-600" : "text-slate-800"}`}>
              {summary.policies_expiring_soon}
            </div>
          </div>
        </div>
      )}

      {/* Tab strip */}
      <div className="flex gap-1 border-b border-slate-200">
        <button
          onClick={() => setTab("policies")}
          className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
            tab === "policies"
              ? "border-indigo-600 text-indigo-600"
              : "border-transparent text-slate-500 hover:text-slate-800 hover:border-slate-300"
          }`}
        >
          <ShieldCheck className="w-4 h-4" /> Policies
        </button>
        <button
          onClick={() => setTab("appraisals")}
          className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
            tab === "appraisals"
              ? "border-indigo-600 text-indigo-600"
              : "border-transparent text-slate-500 hover:text-slate-800 hover:border-slate-300"
          }`}
        >
          <FileSearch className="w-4 h-4" /> Appraisals
        </button>
      </div>

      {/* Tab content */}
      <div>
        {tab === "policies" ? (
          <PoliciesTab assets={assets} onToast={onToast} onSummaryChange={loadSummary} />
        ) : (
          <AppraisalsTab assets={assets} onToast={onToast} onSummaryChange={loadSummary} />
        )}
      </div>
    </div>
  );
}
