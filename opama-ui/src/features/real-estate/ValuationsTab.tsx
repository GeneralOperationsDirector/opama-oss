/**
 * ValuationsTab — Property Records: Valuations.
 *
 * Lists PropertyValuation rows (appraisal, market estimate, or tax
 * assessment history) for the user's "Real Estate" category assets, with
 * create/edit/delete and document upload.
 */
import React, { useEffect, useState } from "react";
import { Plus, Pencil, Trash2, X, Check, Paperclip, ExternalLink } from "lucide-react";
import { api, API_BASE } from "../../lib/api";
import { getAuthToken } from "../../lib/authToken";
import type { CustomAsset } from "../custom-assets/types";
import type { PropertyValuation, PropertyValuationForm } from "./types";

interface Props {
  assets: CustomAsset[];
  onToast: (msg: string, type?: "success" | "error" | "info") => void;
  onSummaryChange: () => void;
}

const SOURCES = ["Appraisal", "Market Estimate", "Tax Assessment", "Other"];

function emptyForm(assets: CustomAsset[]): PropertyValuationForm {
  return {
    asset_id: assets[0]?.id ?? 0,
    valuation_amount: 0,
    valuation_date: "",
    source: SOURCES[0],
    notes: "",
  };
}

function fmtMoney(n: number | null | undefined) {
  if (n == null) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(n);
}

function docUrl(path: string | null) {
  if (!path) return null;
  return path.startsWith("/") ? `${API_BASE}${path}` : path;
}

function cleanPayload(form: PropertyValuationForm): Record<string, unknown> {
  return {
    asset_id: form.asset_id,
    valuation_amount: form.valuation_amount,
    valuation_date: form.valuation_date || null,
    source: form.source || null,
    notes: form.notes || null,
  };
}

function PropertyValuationForm_({
  initial, assets, onSave, onCancel, saving,
}: {
  initial: PropertyValuationForm;
  assets: CustomAsset[];
  onSave: (form: PropertyValuationForm) => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const [form, setForm] = useState<PropertyValuationForm>(initial);
  const set = (key: keyof PropertyValuationForm, val: unknown) => setForm((f) => ({ ...f, [key]: val }));

  return (
    <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-slate-500 mb-0.5 block">Property *</label>
          <select value={form.asset_id || ""} onChange={(e) => set("asset_id", e.target.value ? parseInt(e.target.value, 10) : 0)}
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400">
            <option value="">— select —</option>
            {assets.map((a) => (
              <option key={a.id} value={a.id}>{a.name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs text-slate-500 mb-0.5 block">Source</label>
          <select value={form.source ?? ""} onChange={(e) => set("source", e.target.value)}
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400">
            {SOURCES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-slate-500 mb-0.5 block">Valuation Amount *</label>
          <input type="number" min={0} step="0.01" value={form.valuation_amount}
            onChange={(e) => set("valuation_amount", e.target.value === "" ? 0 : parseFloat(e.target.value))}
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
        </div>
        <div>
          <label className="text-xs text-slate-500 mb-0.5 block">Valuation Date</label>
          <input type="date" value={form.valuation_date ?? ""} onChange={(e) => set("valuation_date", e.target.value)}
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
        </div>
      </div>
      <div>
        <label className="text-xs text-slate-500 mb-0.5 block">Notes</label>
        <textarea value={form.notes ?? ""} onChange={(e) => set("notes", e.target.value)} rows={2}
          className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
      </div>
      <div className="flex gap-2 pt-1">
        <button onClick={() => onSave(form)} disabled={saving || !form.asset_id || !(form.valuation_amount > 0)}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 text-white rounded-lg text-xs font-medium hover:bg-indigo-700 disabled:opacity-50">
          <Check className="w-3.5 h-3.5" />{saving ? "Saving…" : "Save"}
        </button>
        <button onClick={onCancel} className="flex items-center gap-1.5 px-3 py-1.5 border border-slate-200 rounded-lg text-xs text-slate-600 hover:bg-slate-50">
          <X className="w-3.5 h-3.5" />Cancel
        </button>
      </div>
    </div>
  );
}

export default function ValuationsTab({ assets, onToast, onSummaryChange }: Props) {
  const [valuations, setValuations] = useState<PropertyValuation[] | null>(null);
  const [showNewForm, setShowNewForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [uploadingId, setUploadingId] = useState<number | null>(null);

  useEffect(() => {
    api<PropertyValuation[]>("/real-estate/valuations")
      .then(setValuations)
      .catch(() => {
        onToast("Failed to load valuations", "error");
        setValuations([]);
      });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const createValuation = async (form: PropertyValuationForm) => {
    setSaving(true);
    try {
      const created = await api<PropertyValuation>("/real-estate/valuations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cleanPayload(form)),
      });
      setValuations((prev) => [created, ...(prev ?? [])]);
      setShowNewForm(false);
      onSummaryChange();
      onToast("Valuation added", "success");
    } catch {
      onToast("Failed to add valuation", "error");
    } finally {
      setSaving(false);
    }
  };

  const updateValuation = async (id: number, form: PropertyValuationForm) => {
    setSaving(true);
    try {
      const updated = await api<PropertyValuation>(`/real-estate/valuations/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cleanPayload(form)),
      });
      setValuations((prev) => (prev ?? []).map((v) => (v.id === id ? updated : v)));
      setEditingId(null);
      onSummaryChange();
      onToast("Valuation updated", "success");
    } catch {
      onToast("Failed to update valuation", "error");
    } finally {
      setSaving(false);
    }
  };

  const deleteValuation = async (id: number) => {
    if (!confirm("Delete this valuation record?")) return;
    try {
      await api(`/real-estate/valuations/${id}`, { method: "DELETE" });
      setValuations((prev) => (prev ?? []).filter((v) => v.id !== id));
      onSummaryChange();
      onToast("Valuation deleted", "success");
    } catch {
      onToast("Failed to delete valuation", "error");
    }
  };

  const uploadDocument = async (id: number, file: File) => {
    setUploadingId(id);
    try {
      const token = await getAuthToken();
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`${API_BASE}/real-estate/valuations/${id}/document`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: fd,
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const { document_url, document_filename } = await res.json();
      setValuations((prev) => (prev ?? []).map((v) => (v.id === id ? { ...v, document_url, document_filename } : v)));
      onToast("Document uploaded", "success");
    } catch {
      onToast("Failed to upload document", "error");
    } finally {
      setUploadingId(null);
    }
  };

  const valuationToForm = (v: PropertyValuation): PropertyValuationForm => ({
    asset_id: v.asset_id,
    valuation_amount: v.valuation_amount,
    valuation_date: v.valuation_date ?? "",
    source: v.source ?? "",
    notes: v.notes ?? "",
  });

  if (valuations === null) {
    return <div className="py-16 text-center text-slate-400 text-sm">Loading…</div>;
  }

  if (assets.length === 0) {
    return (
      <div className="py-16 text-center text-slate-400 space-y-2">
        <div className="text-4xl">🏠</div>
        <div className="font-medium text-slate-600">No properties yet</div>
        <p className="text-sm">Add a property in Collections first, then come back to track valuations.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {valuations.length === 0 && !showNewForm && (
        <div className="py-16 text-center text-slate-400 space-y-2">
          <div className="text-4xl">📈</div>
          <div className="font-medium text-slate-600">No valuations yet</div>
          <p className="text-sm">Add an appraisal, market estimate, or tax assessment.</p>
        </div>
      )}

      {valuations.map((valuation) => {
        const isEditing = editingId === valuation.id;
        const doc = docUrl(valuation.document_url);
        const asset = assets.find((a) => a.id === valuation.asset_id);
        return (
          <div key={valuation.id} className="bg-white border border-slate-200 rounded-xl p-4 space-y-2">
            {isEditing ? (
              <PropertyValuationForm_
                initial={valuationToForm(valuation)}
                assets={assets}
                onSave={(form) => updateValuation(valuation.id, form)}
                onCancel={() => setEditingId(null)}
                saving={saving}
              />
            ) : (
              <>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="font-semibold text-slate-800">{fmtMoney(valuation.valuation_amount)}</div>
                    <div className="flex gap-1.5 mt-1 flex-wrap text-xs">
                      {asset && <span className="bg-violet-50 text-violet-700 px-2 py-0.5 rounded-full">{asset.name}</span>}
                      {valuation.source && <span className="bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded-full">{valuation.source}</span>}
                      {valuation.valuation_date && <span className="bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">{valuation.valuation_date}</span>}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <button onClick={() => setEditingId(valuation.id)} className="text-slate-400 hover:text-indigo-600 p-1">
                      <Pencil className="w-4 h-4" />
                    </button>
                    <button onClick={() => deleteValuation(valuation.id)} className="text-slate-400 hover:text-red-600 p-1">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {valuation.notes && <p className="text-xs text-slate-500">{valuation.notes}</p>}

                <div className="flex items-center justify-end pt-2 border-t border-slate-100 text-xs">
                  {doc && (
                    <a href={doc} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-indigo-600 hover:underline mr-2">
                      <ExternalLink className="w-3.5 h-3.5" />{valuation.document_filename || "Document"}
                    </a>
                  )}
                  <label className="flex items-center gap-1 text-slate-500 hover:text-indigo-600 cursor-pointer">
                    <Paperclip className="w-3.5 h-3.5" />
                    {uploadingId === valuation.id ? "Uploading…" : doc ? "Replace" : "Upload document"}
                    <input type="file" accept=".pdf,.jpg,.jpeg,.png,.webp" className="hidden"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) uploadDocument(valuation.id, file);
                        e.target.value = "";
                      }} />
                  </label>
                </div>
              </>
            )}
          </div>
        );
      })}

      {showNewForm ? (
        <PropertyValuationForm_ initial={emptyForm(assets)} assets={assets} onSave={createValuation} onCancel={() => setShowNewForm(false)} saving={saving} />
      ) : (
        <button onClick={() => setShowNewForm(true)}
          className="flex items-center gap-1.5 text-sm text-indigo-600 hover:text-indigo-800 font-medium">
          <Plus className="w-4 h-4" />Add Valuation
        </button>
      )}
    </div>
  );
}
