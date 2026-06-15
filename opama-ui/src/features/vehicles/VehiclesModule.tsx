/**
 * VehiclesModule — Vehicle Maintenance.
 *
 * Two tabs: Service Log (maintenance/service history per vehicle) and
 * Documents (registration, title, insurance card, inspection). Backend:
 * services/vehicles. Every record links to a CustomAsset in the "Vehicle"
 * or "Bicycle" category — the asset pickers in each tab are pre-filtered to
 * those categories. Vehicles/bicycles themselves are added/removed from
 * Collections (onNavigate jumps there with the right template).
 */
import React, { useCallback, useEffect, useState } from "react";
import { Wrench, FileText, Plus } from "lucide-react";
import { api } from "../../lib/api";
import type { AppModule } from "../../types";
import type { CustomAsset } from "../custom-assets/types";
import type { VehicleSummary } from "./types";
import ServiceLogTab from "./ServiceLogTab";
import DocumentsTab from "./DocumentsTab";

interface Props {
  userId: number;
  onToast: (msg: string, type?: "success" | "error" | "info") => void;
  onNavigate: (module: AppModule, tab?: string, templateId?: string) => void;
}

type Tab = "service-log" | "documents";

function fmtUSD(n: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD", maximumFractionDigits: 0,
  }).format(n);
}

export default function VehiclesModule({ onToast, onNavigate }: Props) {
  const [tab, setTab] = useState<Tab>("service-log");
  const [summary, setSummary] = useState<VehicleSummary | null>(null);
  const [assets, setAssets] = useState<CustomAsset[]>([]);

  const loadSummary = useCallback(async () => {
    try {
      const s = await api<VehicleSummary>("/vehicles/summary");
      setSummary(s);
    } catch {
      onToast("Failed to load vehicle summary", "error");
    }
  }, [onToast]);

  useEffect(() => {
    loadSummary();
    api<CustomAsset[]>("/assets").then(setAssets).catch(() => setAssets([]));
  }, [loadSummary]);

  const vehicleAssets = assets.filter((a) => ["vehicle", "bicycle"].includes(a.category.toLowerCase()));

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
            🚗 Vehicle Maintenance
          </h2>
          <p className="text-sm text-slate-500 mt-0.5">
            Track service history, mileage, and registration/title documents for your vehicles and bicycles.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => onNavigate("custom", undefined, "car")}
            className="flex items-center gap-1.5 px-3 py-1.5 border border-slate-200 rounded-lg text-xs font-medium text-slate-600 hover:bg-slate-50"
          >
            <Plus className="w-3.5 h-3.5" />🚗 Add Vehicle
          </button>
          <button
            onClick={() => onNavigate("custom", undefined, "bicycle")}
            className="flex items-center gap-1.5 px-3 py-1.5 border border-slate-200 rounded-lg text-xs font-medium text-slate-600 hover:bg-slate-50"
          >
            <Plus className="w-3.5 h-3.5" />🚲 Add Bicycle
          </button>
        </div>
      </div>

      {/* Summary strip */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="bg-white border border-slate-200 rounded-xl p-3">
            <div className="text-xs text-slate-400 uppercase tracking-wide">Vehicles</div>
            <div className="text-lg font-semibold text-slate-800">{summary.vehicle_count}</div>
          </div>
          <div className="bg-white border border-slate-200 rounded-xl p-3">
            <div className="text-xs text-slate-400 uppercase tracking-wide">Total Service Cost</div>
            <div className="text-lg font-semibold text-slate-800">{fmtUSD(summary.total_service_cost)}</div>
          </div>
          <div className="bg-white border border-slate-200 rounded-xl p-3">
            <div className="text-xs text-slate-400 uppercase tracking-wide">Service Records</div>
            <div className="text-lg font-semibold text-slate-800">{summary.service_record_count}</div>
          </div>
          <div className="bg-white border border-slate-200 rounded-xl p-3">
            <div className="text-xs text-slate-400 uppercase tracking-wide">Docs Expiring (60d)</div>
            <div className={`text-lg font-semibold ${summary.documents_expiring_soon > 0 ? "text-amber-600" : "text-slate-800"}`}>
              {summary.documents_expiring_soon}
            </div>
          </div>
        </div>
      )}

      {/* Tab strip */}
      <div className="flex gap-1 border-b border-slate-200">
        <button
          onClick={() => setTab("service-log")}
          className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
            tab === "service-log"
              ? "border-indigo-600 text-indigo-600"
              : "border-transparent text-slate-500 hover:text-slate-800 hover:border-slate-300"
          }`}
        >
          <Wrench className="w-4 h-4" /> Service Log
        </button>
        <button
          onClick={() => setTab("documents")}
          className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
            tab === "documents"
              ? "border-indigo-600 text-indigo-600"
              : "border-transparent text-slate-500 hover:text-slate-800 hover:border-slate-300"
          }`}
        >
          <FileText className="w-4 h-4" /> Documents
        </button>
      </div>

      {/* Tab content */}
      <div>
        {tab === "service-log" ? (
          <ServiceLogTab assets={vehicleAssets} onToast={onToast} onSummaryChange={loadSummary} onNavigate={onNavigate} />
        ) : (
          <DocumentsTab assets={vehicleAssets} onToast={onToast} onSummaryChange={loadSummary} onNavigate={onNavigate} />
        )}
      </div>
    </div>
  );
}
