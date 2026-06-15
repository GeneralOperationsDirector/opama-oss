/**
 * PropertyTaxTab — Property Records: Property Tax.
 *
 * Lists PropertyTaxRecord rows (annual tax bills with assessed value, tax
 * amount, due date, and paid status) for the user's "Real Estate" category
 * assets, with create/edit/delete and document upload. Unpaid records due
 * within 60 days are highlighted.
 */
import React, { useEffect, useState } from "react";
import { Plus, Pencil, Trash2, X, Check, Paperclip, ExternalLink } from "lucide-react";
import { api, API_BASE } from "../../lib/api";
import { getAuthToken } from "../../lib/authToken";
import type { CustomAsset } from "../custom-assets/types";
import type { PropertyTaxRecord, PropertyTaxRecordForm } from "./types";

interface Props {
  assets: CustomAsset[];
  onToast: (msg: string, type?: "success" | "error" | "info") => void;
  onSummaryChange: () => void;
}

function emptyForm(assets: CustomAsset[]): PropertyTaxRecordForm {
  return {
    asset_id: assets[0]?.id ?? 0,
    tax_year: new Date().getFullYear(),
    assessed_value: null,
    tax_amount: null,
    due_date: "",
    paid: false,
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

function cleanPayload(form: PropertyTaxRecordForm): Record<string, unknown> {
  return {
    asset_id: form.asset_id,
    tax_year: form.tax_year,
    assessed_value: form.assessed_value,
    tax_amount: form.tax_amount,
    due_date: form.due_date || null,
    paid: form.paid,
    notes: form.notes || null,
  };
}

function isDueSoon(dueDate: string | null, paid: boolean): boolean {
  if (paid || !dueDate) return false;
  const today = new Date().toISOString().slice(0, 10);
  const cutoff = new Date(Date.now() + 60 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
  return dueDate >= today && dueDate <= cutoff;
}

function PropertyTaxRecordForm_({
  initial, assets, onSave, onCancel, saving,
}: {
  initial: PropertyTaxRecordForm;
  assets: CustomAsset[];
  onSave: (form: PropertyTaxRecordForm) => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const [form, setForm] = useState<PropertyTaxRecordForm>(initial);
  const set = (key: keyof PropertyTaxRecordForm, val: unknown) => setForm((f) => ({ ...f, [key]: val }));

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
          <label className="text-xs text-slate-500 mb-0.5 block">Tax Year *</label>
          <input type="number" value={form.tax_year}
            onChange={(e) => set("tax_year", e.target.value === "" ? new Date().getFullYear() : parseInt(e.target.value, 10))}
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-slate-500 mb-0.5 block">Assessed Value</label>
          <input type="number" min={0} step="0.01" value={form.assessed_value ?? ""}
            onChange={(e) => set("assessed_value", e.target.value === "" ? null : parseFloat(e.target.value))}
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
        </div>
        <div>
          <label className="text-xs text-slate-500 mb-0.5 block">Tax Amount</label>
          <input type="number" min={0} step="0.01" value={form.tax_amount ?? ""}
            onChange={(e) => set("tax_amount", e.target.value === "" ? null : parseFloat(e.target.value))}
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3 items-end">
        <div>
          <label className="text-xs text-slate-500 mb-0.5 block">Due Date</label>
          <input type="date" value={form.due_date ?? ""} onChange={(e) => set("due_date", e.target.value)}
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
        </div>
        <div>
          <label className="flex items-center gap-1.5 text-xs text-slate-500 mb-0.5">
            <input type="checkbox" checked={form.paid} onChange={(e) => set("paid", e.target.checked)}
              className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-400" />
            Paid
          </label>
        </div>
      </div>
      <div>
        <label className="text-xs text-slate-500 mb-0.5 block">Notes</label>
        <textarea value={form.notes ?? ""} onChange={(e) => set("notes", e.target.value)} rows={2}
          className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
      </div>
      <div className="flex gap-2 pt-1">
        <button onClick={() => onSave(form)} disabled={saving || !form.asset_id || !form.tax_year}
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

export default function PropertyTaxTab({ assets, onToast, onSummaryChange }: Props) {
  const [records, setRecords] = useState<PropertyTaxRecord[] | null>(null);
  const [showNewForm, setShowNewForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [uploadingId, setUploadingId] = useState<number | null>(null);

  useEffect(() => {
    api<PropertyTaxRecord[]>("/real-estate/tax-records")
      .then(setRecords)
      .catch(() => {
        onToast("Failed to load tax records", "error");
        setRecords([]);
      });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const createRecord = async (form: PropertyTaxRecordForm) => {
    setSaving(true);
    try {
      const created = await api<PropertyTaxRecord>("/real-estate/tax-records", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cleanPayload(form)),
      });
      setRecords((prev) => [created, ...(prev ?? [])]);
      setShowNewForm(false);
      onSummaryChange();
      onToast("Tax record added", "success");
    } catch {
      onToast("Failed to add tax record", "error");
    } finally {
      setSaving(false);
    }
  };

  const updateRecord = async (id: number, form: PropertyTaxRecordForm) => {
    setSaving(true);
    try {
      const updated = await api<PropertyTaxRecord>(`/real-estate/tax-records/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cleanPayload(form)),
      });
      setRecords((prev) => (prev ?? []).map((r) => (r.id === id ? updated : r)));
      setEditingId(null);
      onSummaryChange();
      onToast("Tax record updated", "success");
    } catch {
      onToast("Failed to update tax record", "error");
    } finally {
      setSaving(false);
    }
  };

  const deleteRecord = async (id: number) => {
    if (!confirm("Delete this tax record?")) return;
    try {
      await api(`/real-estate/tax-records/${id}`, { method: "DELETE" });
      setRecords((prev) => (prev ?? []).filter((r) => r.id !== id));
      onSummaryChange();
      onToast("Tax record deleted", "success");
    } catch {
      onToast("Failed to delete tax record", "error");
    }
  };

  const uploadDocument = async (id: number, file: File) => {
    setUploadingId(id);
    try {
      const token = await getAuthToken();
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`${API_BASE}/real-estate/tax-records/${id}/document`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: fd,
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const { document_url, document_filename } = await res.json();
      setRecords((prev) => (prev ?? []).map((r) => (r.id === id ? { ...r, document_url, document_filename } : r)));
      onToast("Document uploaded", "success");
    } catch {
      onToast("Failed to upload document", "error");
    } finally {
      setUploadingId(null);
    }
  };

  const recordToForm = (r: PropertyTaxRecord): PropertyTaxRecordForm => ({
    asset_id: r.asset_id,
    tax_year: r.tax_year,
    assessed_value: r.assessed_value,
    tax_amount: r.tax_amount,
    due_date: r.due_date ?? "",
    paid: r.paid,
    notes: r.notes ?? "",
  });

  if (records === null) {
    return <div className="py-16 text-center text-slate-400 text-sm">Loading…</div>;
  }

  if (assets.length === 0) {
    return (
      <div className="py-16 text-center text-slate-400 space-y-2">
        <div className="text-4xl">🏠</div>
        <div className="font-medium text-slate-600">No properties yet</div>
        <p className="text-sm">Add a property in Collections first, then come back to track tax records.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {records.length === 0 && !showNewForm && (
        <div className="py-16 text-center text-slate-400 space-y-2">
          <div className="text-4xl">🧾</div>
          <div className="font-medium text-slate-600">No tax records yet</div>
          <p className="text-sm">Add a property tax bill to track due dates and payment status.</p>
        </div>
      )}

      {records.map((record) => {
        const isEditing = editingId === record.id;
        const doc = docUrl(record.document_url);
        const asset = assets.find((a) => a.id === record.asset_id);
        const dueSoon = isDueSoon(record.due_date, record.paid);
        return (
          <div key={record.id} className="bg-white border border-slate-200 rounded-xl p-4 space-y-2">
            {isEditing ? (
              <PropertyTaxRecordForm_
                initial={recordToForm(record)}
                assets={assets}
                onSave={(form) => updateRecord(record.id, form)}
                onCancel={() => setEditingId(null)}
                saving={saving}
              />
            ) : (
              <>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="font-semibold text-slate-800">Tax Year {record.tax_year}</div>
                    <div className="flex gap-1.5 mt-1 flex-wrap text-xs">
                      {asset && <span className="bg-violet-50 text-violet-700 px-2 py-0.5 rounded-full">{asset.name}</span>}
                      <span className={`px-2 py-0.5 rounded-full ${record.paid ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}`}>
                        {record.paid ? "Paid" : "Unpaid"}
                      </span>
                      {record.due_date && (
                        <span className={`px-2 py-0.5 rounded-full ${dueSoon ? "bg-amber-100 text-amber-700 font-medium" : "bg-slate-100 text-slate-600"}`}>
                          due {record.due_date}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <div className="text-sm font-semibold text-slate-700 mr-2">{fmtMoney(record.tax_amount)}</div>
                    <button onClick={() => setEditingId(record.id)} className="text-slate-400 hover:text-indigo-600 p-1">
                      <Pencil className="w-4 h-4" />
                    </button>
                    <button onClick={() => deleteRecord(record.id)} className="text-slate-400 hover:text-red-600 p-1">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {record.assessed_value != null && (
                  <div className="text-xs text-slate-600"><span className="text-slate-400">Assessed Value: </span>{fmtMoney(record.assessed_value)}</div>
                )}

                {record.notes && <p className="text-xs text-slate-500">{record.notes}</p>}

                <div className="flex items-center justify-end pt-2 border-t border-slate-100 text-xs">
                  {doc && (
                    <a href={doc} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-indigo-600 hover:underline mr-2">
                      <ExternalLink className="w-3.5 h-3.5" />{record.document_filename || "Document"}
                    </a>
                  )}
                  <label className="flex items-center gap-1 text-slate-500 hover:text-indigo-600 cursor-pointer">
                    <Paperclip className="w-3.5 h-3.5" />
                    {uploadingId === record.id ? "Uploading…" : doc ? "Replace" : "Upload document"}
                    <input type="file" accept=".pdf,.jpg,.jpeg,.png,.webp" className="hidden"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) uploadDocument(record.id, file);
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
        <PropertyTaxRecordForm_ initial={emptyForm(assets)} assets={assets} onSave={createRecord} onCancel={() => setShowNewForm(false)} saving={saving} />
      ) : (
        <button onClick={() => setShowNewForm(true)}
          className="flex items-center gap-1.5 text-sm text-indigo-600 hover:text-indigo-800 font-medium">
          <Plus className="w-4 h-4" />Add Tax Record
        </button>
      )}
    </div>
  );
}
