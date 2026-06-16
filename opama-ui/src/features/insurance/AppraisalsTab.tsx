/**
 * AppraisalsTab — Insurance & Appraisals: Appraisals.
 *
 * Lists Appraisal records (standalone or linked to a CustomAsset) with
 * create/edit/delete and document upload. Optional filter narrows the list
 * to appraisals linked to a specific collection asset.
 */
import React, { useEffect, useState } from "react";
import { Plus, Pencil, Trash2, X, Check, Paperclip, ExternalLink } from "lucide-react";
import { api, API_BASE } from "../../lib/api";
import { getAuthToken } from "../../lib/authToken";
import type { CustomAsset } from "../custom-assets/types";
import type { Appraisal, AppraisalForm } from "./types";

interface Props {
  assets: CustomAsset[];
  onToast: (msg: string, type?: "success" | "error" | "info") => void;
  onSummaryChange: () => void;
}

const EMPTY_FORM: AppraisalForm = {
  asset_id: null,
  appraiser_name: "",
  appraised_value: 0,
  appraisal_date: "",
  notes: "",
};

function fmtMoney(n: number | null | undefined) {
  if (n == null) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(n);
}

function docUrl(path: string | null) {
  if (!path) return null;
  return path.startsWith("/") ? `${API_BASE}${path}` : path;
}

function cleanPayload(form: AppraisalForm): Record<string, unknown> {
  return {
    asset_id: form.asset_id || null,
    appraiser_name: form.appraiser_name || null,
    appraised_value: form.appraised_value,
    appraisal_date: form.appraisal_date || null,
    notes: form.notes || null,
  };
}

function AppraisalForm_({
  initial, assets, onSave, onCancel, saving,
}: {
  initial: AppraisalForm;
  assets: CustomAsset[];
  onSave: (form: AppraisalForm) => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const [form, setForm] = useState<AppraisalForm>(initial);
  const set = (key: keyof AppraisalForm, val: unknown) => setForm((f) => ({ ...f, [key]: val }));

  return (
    <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-slate-500 mb-0.5 block">Linked Asset (optional)</label>
          <select value={form.asset_id ?? ""} onChange={(e) => set("asset_id", e.target.value ? parseInt(e.target.value, 10) : null)}
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400">
            <option value="">— none —</option>
            {assets.map((a) => (
              <option key={a.id} value={a.id}>{a.name} ({a.category})</option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs text-slate-500 mb-0.5 block">Appraiser</label>
          <input value={form.appraiser_name ?? ""} onChange={(e) => set("appraiser_name", e.target.value)}
            placeholder="e.g. Jane Smith, GIA"
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-slate-500 mb-0.5 block">Appraised Value *</label>
          <input type="number" min={0} step="0.01" value={form.appraised_value}
            onChange={(e) => set("appraised_value", e.target.value === "" ? 0 : parseFloat(e.target.value))}
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
        </div>
        <div>
          <label className="text-xs text-slate-500 mb-0.5 block">Appraisal Date</label>
          <input type="date" value={form.appraisal_date ?? ""} onChange={(e) => set("appraisal_date", e.target.value)}
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
        </div>
      </div>
      <div>
        <label className="text-xs text-slate-500 mb-0.5 block">Notes</label>
        <textarea value={form.notes ?? ""} onChange={(e) => set("notes", e.target.value)} rows={2}
          className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
      </div>
      <div className="flex gap-2 pt-1">
        <button onClick={() => onSave(form)} disabled={saving || !(form.appraised_value > 0)}
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

export default function AppraisalsTab({ assets, onToast, onSummaryChange }: Props) {
  const [appraisals, setAppraisals] = useState<Appraisal[] | null>(null);
  const [showNewForm, setShowNewForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [uploadingId, setUploadingId] = useState<number | null>(null);

  useEffect(() => {
    api<Appraisal[]>("/insurance/appraisals")
      .then(setAppraisals)
      .catch(() => {
        onToast("Failed to load appraisals", "error");
        setAppraisals([]);
      });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const createAppraisal = async (form: AppraisalForm) => {
    setSaving(true);
    try {
      const created = await api<Appraisal>("/insurance/appraisals", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cleanPayload(form)),
      });
      setAppraisals((prev) => [created, ...(prev ?? [])]);
      setShowNewForm(false);
      onSummaryChange();
      onToast("Appraisal added", "success");
    } catch {
      onToast("Failed to add appraisal", "error");
    } finally {
      setSaving(false);
    }
  };

  const updateAppraisal = async (id: number, form: AppraisalForm) => {
    setSaving(true);
    try {
      const updated = await api<Appraisal>(`/insurance/appraisals/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cleanPayload(form)),
      });
      setAppraisals((prev) => (prev ?? []).map((a) => (a.id === id ? updated : a)));
      setEditingId(null);
      onSummaryChange();
      onToast("Appraisal updated", "success");
    } catch {
      onToast("Failed to update appraisal", "error");
    } finally {
      setSaving(false);
    }
  };

  const deleteAppraisal = async (id: number) => {
    if (!confirm("Delete this appraisal record?")) return;
    try {
      await api(`/insurance/appraisals/${id}`, { method: "DELETE" });
      setAppraisals((prev) => (prev ?? []).filter((a) => a.id !== id));
      onSummaryChange();
      onToast("Appraisal deleted", "success");
    } catch {
      onToast("Failed to delete appraisal", "error");
    }
  };

  const uploadDocument = async (id: number, file: File) => {
    setUploadingId(id);
    try {
      const token = await getAuthToken();
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`${API_BASE}/insurance/appraisals/${id}/document`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: fd,
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const { document_url, document_filename } = await res.json();
      setAppraisals((prev) => (prev ?? []).map((a) => (a.id === id ? { ...a, document_url, document_filename } : a)));
      onToast("Document uploaded", "success");
    } catch {
      onToast("Failed to upload document", "error");
    } finally {
      setUploadingId(null);
    }
  };

  const appraisalToForm = (a: Appraisal): AppraisalForm => ({
    asset_id: a.asset_id,
    appraiser_name: a.appraiser_name ?? "",
    appraised_value: a.appraised_value,
    appraisal_date: a.appraisal_date ?? "",
    notes: a.notes ?? "",
  });

  if (appraisals === null) {
    return <div className="py-16 text-center text-slate-400 text-sm">Loading…</div>;
  }

  return (
    <div className="space-y-3">
      {appraisals.length === 0 && !showNewForm && (
        <div className="py-16 text-center text-slate-400 space-y-2">
          <div className="text-4xl">📋</div>
          <div className="font-medium text-slate-600">No appraisal records yet</div>
          <p className="text-sm">Add an appraisal to document the value of an item.</p>
        </div>
      )}

      {appraisals.map((appraisal) => {
        const isEditing = editingId === appraisal.id;
        const doc = docUrl(appraisal.document_url);
        const asset = assets.find((a) => a.id === appraisal.asset_id);
        return (
          <div key={appraisal.id} className="bg-white border border-slate-200 rounded-xl p-4 space-y-2">
            {isEditing ? (
              <AppraisalForm_
                initial={appraisalToForm(appraisal)}
                assets={assets}
                onSave={(form) => updateAppraisal(appraisal.id, form)}
                onCancel={() => setEditingId(null)}
                saving={saving}
              />
            ) : (
              <>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="font-semibold text-slate-800">{fmtMoney(appraisal.appraised_value)}</div>
                    <div className="flex gap-1.5 mt-1 flex-wrap text-xs">
                      {appraisal.appraiser_name && <span className="bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded-full">{appraisal.appraiser_name}</span>}
                      {appraisal.appraisal_date && <span className="bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">{appraisal.appraisal_date}</span>}
                      {asset && <span className="bg-violet-50 text-violet-700 px-2 py-0.5 rounded-full">linked: {asset.name}</span>}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <button onClick={() => setEditingId(appraisal.id)} className="text-slate-400 hover:text-indigo-600 p-1">
                      <Pencil className="w-4 h-4" />
                    </button>
                    <button onClick={() => deleteAppraisal(appraisal.id)} className="text-slate-400 hover:text-red-600 p-1">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {appraisal.notes && <p className="text-xs text-slate-500">{appraisal.notes}</p>}

                <div className="flex items-center justify-end pt-2 border-t border-slate-100 text-xs">
                  {doc && (
                    <a href={doc} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-indigo-600 hover:underline mr-2">
                      <ExternalLink className="w-3.5 h-3.5" />{appraisal.document_filename || "Document"}
                    </a>
                  )}
                  <label className="flex items-center gap-1 text-slate-500 hover:text-indigo-600 cursor-pointer">
                    <Paperclip className="w-3.5 h-3.5" />
                    {uploadingId === appraisal.id ? "Uploading…" : doc ? "Replace" : "Upload document"}
                    <input type="file" accept=".pdf,.jpg,.jpeg,.png,.webp" className="hidden"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) uploadDocument(appraisal.id, file);
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
        <AppraisalForm_ initial={EMPTY_FORM} assets={assets} onSave={createAppraisal} onCancel={() => setShowNewForm(false)} saving={saving} />
      ) : (
        <button onClick={() => setShowNewForm(true)}
          className="flex items-center gap-1.5 text-sm text-indigo-600 hover:text-indigo-800 font-medium">
          <Plus className="w-4 h-4" />Add Appraisal
        </button>
      )}
    </div>
  );
}
