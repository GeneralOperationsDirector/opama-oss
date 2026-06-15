/**
 * ServiceLogTab — Vehicle Maintenance: Service Log.
 *
 * Lists ServiceRecord rows (maintenance/service history) for the user's
 * "Vehicle" category assets, with create/edit/delete and receipt upload.
 * Every record must link to a vehicle asset — if the user has none yet,
 * shows a hint to add one in Collections first.
 */
import React, { useEffect, useState } from "react";
import { Plus, Pencil, Trash2, X, Check, Paperclip, ExternalLink } from "lucide-react";
import { api, API_BASE } from "../../lib/api";
import { getAuthToken } from "../../lib/authToken";
import type { AppModule } from "../../types";
import type { CustomAsset } from "../custom-assets/types";
import type { ServiceRecord, ServiceRecordForm } from "./types";

interface Props {
  assets: CustomAsset[];
  onToast: (msg: string, type?: "success" | "error" | "info") => void;
  onSummaryChange: () => void;
  onNavigate: (module: AppModule, tab?: string, templateId?: string) => void;
}

function emptyForm(assets: CustomAsset[]): ServiceRecordForm {
  return {
    asset_id: assets[0]?.id ?? 0,
    service_date: "",
    odometer: null,
    service_type: "",
    cost: null,
    vendor: "",
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

function cleanPayload(form: ServiceRecordForm): Record<string, unknown> {
  return {
    asset_id: form.asset_id,
    service_date: form.service_date || null,
    odometer: form.odometer,
    service_type: form.service_type,
    cost: form.cost,
    vendor: form.vendor || null,
    notes: form.notes || null,
  };
}

function ServiceRecordForm_({
  initial, assets, onSave, onCancel, saving,
}: {
  initial: ServiceRecordForm;
  assets: CustomAsset[];
  onSave: (form: ServiceRecordForm) => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const [form, setForm] = useState<ServiceRecordForm>(initial);
  const set = (key: keyof ServiceRecordForm, val: unknown) => setForm((f) => ({ ...f, [key]: val }));

  return (
    <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-slate-500 mb-0.5 block">Vehicle *</label>
          <select value={form.asset_id || ""} onChange={(e) => set("asset_id", e.target.value ? parseInt(e.target.value, 10) : 0)}
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400">
            <option value="">— select —</option>
            {assets.map((a) => (
              <option key={a.id} value={a.id}>{a.name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs text-slate-500 mb-0.5 block">Service Type *</label>
          <input value={form.service_type} onChange={(e) => set("service_type", e.target.value)}
            placeholder="e.g. Oil Change"
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
        </div>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div>
          <label className="text-xs text-slate-500 mb-0.5 block">Service Date</label>
          <input type="date" value={form.service_date ?? ""} onChange={(e) => set("service_date", e.target.value)}
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
        </div>
        <div>
          <label className="text-xs text-slate-500 mb-0.5 block">Odometer</label>
          <input type="number" min={0} value={form.odometer ?? ""}
            onChange={(e) => set("odometer", e.target.value === "" ? null : parseInt(e.target.value, 10))}
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
        </div>
        <div>
          <label className="text-xs text-slate-500 mb-0.5 block">Cost</label>
          <input type="number" min={0} step="0.01" value={form.cost ?? ""}
            onChange={(e) => set("cost", e.target.value === "" ? null : parseFloat(e.target.value))}
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
        </div>
      </div>
      <div>
        <label className="text-xs text-slate-500 mb-0.5 block">Vendor</label>
        <input value={form.vendor ?? ""} onChange={(e) => set("vendor", e.target.value)}
          placeholder="e.g. Jiffy Lube"
          className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
      </div>
      <div>
        <label className="text-xs text-slate-500 mb-0.5 block">Notes</label>
        <textarea value={form.notes ?? ""} onChange={(e) => set("notes", e.target.value)} rows={2}
          className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
      </div>
      <div className="flex gap-2 pt-1">
        <button onClick={() => onSave(form)} disabled={saving || !form.asset_id || !form.service_type.trim()}
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

export default function ServiceLogTab({ assets, onToast, onSummaryChange, onNavigate }: Props) {
  const [records, setRecords] = useState<ServiceRecord[] | null>(null);
  const [showNewForm, setShowNewForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [uploadingId, setUploadingId] = useState<number | null>(null);

  useEffect(() => {
    api<ServiceRecord[]>("/vehicles/service-records")
      .then(setRecords)
      .catch(() => {
        onToast("Failed to load service records", "error");
        setRecords([]);
      });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const createRecord = async (form: ServiceRecordForm) => {
    setSaving(true);
    try {
      const created = await api<ServiceRecord>("/vehicles/service-records", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cleanPayload(form)),
      });
      setRecords((prev) => [created, ...(prev ?? [])]);
      setShowNewForm(false);
      onSummaryChange();
      onToast("Service record added", "success");
    } catch {
      onToast("Failed to add service record", "error");
    } finally {
      setSaving(false);
    }
  };

  const updateRecord = async (id: number, form: ServiceRecordForm) => {
    setSaving(true);
    try {
      const updated = await api<ServiceRecord>(`/vehicles/service-records/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cleanPayload(form)),
      });
      setRecords((prev) => (prev ?? []).map((r) => (r.id === id ? updated : r)));
      setEditingId(null);
      onSummaryChange();
      onToast("Service record updated", "success");
    } catch {
      onToast("Failed to update service record", "error");
    } finally {
      setSaving(false);
    }
  };

  const deleteRecord = async (id: number) => {
    if (!confirm("Delete this service record?")) return;
    try {
      await api(`/vehicles/service-records/${id}`, { method: "DELETE" });
      setRecords((prev) => (prev ?? []).filter((r) => r.id !== id));
      onSummaryChange();
      onToast("Service record deleted", "success");
    } catch {
      onToast("Failed to delete service record", "error");
    }
  };

  const uploadDocument = async (id: number, file: File) => {
    setUploadingId(id);
    try {
      const token = await getAuthToken();
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`${API_BASE}/vehicles/service-records/${id}/document`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: fd,
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const { document_url, document_filename } = await res.json();
      setRecords((prev) => (prev ?? []).map((r) => (r.id === id ? { ...r, document_url, document_filename } : r)));
      onToast("Receipt uploaded", "success");
    } catch {
      onToast("Failed to upload receipt", "error");
    } finally {
      setUploadingId(null);
    }
  };

  const recordToForm = (r: ServiceRecord): ServiceRecordForm => ({
    asset_id: r.asset_id,
    service_date: r.service_date ?? "",
    odometer: r.odometer,
    service_type: r.service_type,
    cost: r.cost,
    vendor: r.vendor ?? "",
    notes: r.notes ?? "",
  });

  if (records === null) {
    return <div className="py-16 text-center text-slate-400 text-sm">Loading…</div>;
  }

  if (assets.length === 0) {
    return (
      <div className="py-16 text-center text-slate-400 space-y-3">
        <div className="text-4xl">🚗</div>
        <div className="font-medium text-slate-600">No vehicles or bicycles yet</div>
        <p className="text-sm">Add one to your collection first, then come back to log service records.</p>
        <div className="flex gap-2 justify-center pt-1">
          <button onClick={() => onNavigate("custom", undefined, "car")}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 text-white rounded-lg text-xs font-medium hover:bg-indigo-700">
            <Plus className="w-3.5 h-3.5" />🚗 Add Vehicle
          </button>
          <button onClick={() => onNavigate("custom", undefined, "bicycle")}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 text-white rounded-lg text-xs font-medium hover:bg-indigo-700">
            <Plus className="w-3.5 h-3.5" />🚲 Add Bicycle
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {records.length === 0 && !showNewForm && (
        <div className="py-16 text-center text-slate-400 space-y-2">
          <div className="text-4xl">🔧</div>
          <div className="font-medium text-slate-600">No service records yet</div>
          <p className="text-sm">Log an oil change, tire rotation, or repair to start tracking history.</p>
        </div>
      )}

      {records.map((record) => {
        const isEditing = editingId === record.id;
        const doc = docUrl(record.document_url);
        const asset = assets.find((a) => a.id === record.asset_id);
        return (
          <div key={record.id} className="bg-white border border-slate-200 rounded-xl p-4 space-y-2">
            {isEditing ? (
              <ServiceRecordForm_
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
                    <div className="font-semibold text-slate-800">{record.service_type}</div>
                    <div className="flex gap-1.5 mt-1 flex-wrap text-xs">
                      {asset && <span className="bg-violet-50 text-violet-700 px-2 py-0.5 rounded-full">{asset.name}</span>}
                      {record.service_date && <span className="bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">{record.service_date}</span>}
                      {record.odometer != null && <span className="bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">{record.odometer.toLocaleString()} mi</span>}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <div className="text-sm font-semibold text-slate-700 mr-2">{fmtMoney(record.cost)}</div>
                    <button onClick={() => setEditingId(record.id)} className="text-slate-400 hover:text-indigo-600 p-1">
                      <Pencil className="w-4 h-4" />
                    </button>
                    <button onClick={() => deleteRecord(record.id)} className="text-slate-400 hover:text-red-600 p-1">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {record.vendor && <p className="text-xs text-slate-500"><span className="text-slate-400">Vendor: </span>{record.vendor}</p>}
                {record.notes && <p className="text-xs text-slate-500">{record.notes}</p>}

                <div className="flex items-center justify-end pt-2 border-t border-slate-100 text-xs">
                  {doc && (
                    <a href={doc} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-indigo-600 hover:underline mr-2">
                      <ExternalLink className="w-3.5 h-3.5" />{record.document_filename || "Receipt"}
                    </a>
                  )}
                  <label className="flex items-center gap-1 text-slate-500 hover:text-indigo-600 cursor-pointer">
                    <Paperclip className="w-3.5 h-3.5" />
                    {uploadingId === record.id ? "Uploading…" : doc ? "Replace" : "Upload receipt"}
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
        <ServiceRecordForm_ initial={emptyForm(assets)} assets={assets} onSave={createRecord} onCancel={() => setShowNewForm(false)} saving={saving} />
      ) : (
        <button onClick={() => setShowNewForm(true)}
          className="flex items-center gap-1.5 text-sm text-indigo-600 hover:text-indigo-800 font-medium">
          <Plus className="w-4 h-4" />Add Service Record
        </button>
      )}
    </div>
  );
}
