/**
 * DocumentsTab — Vehicle Maintenance: Documents.
 *
 * Lists VehicleDocument rows (registration, title, insurance card,
 * inspection, ...) for the user's "Vehicle" category assets, with
 * create/edit/delete and document upload. Expiry dates within 60 days are
 * highlighted, mirroring the insurance renewal badge.
 */
import React, { useEffect, useState } from "react";
import { Plus, Pencil, Trash2, X, Check, Paperclip, ExternalLink } from "lucide-react";
import { api, API_BASE } from "../../lib/api";
import { getAuthToken } from "../../lib/authToken";
import { orgHeader } from "../../lib/activeOrg";
import type { AppModule } from "../../types";
import type { CustomAsset } from "../custom-assets/types";
import type { VehicleDocument, VehicleDocumentForm } from "./types";

interface Props {
  assets: CustomAsset[];
  onToast: (msg: string, type?: "success" | "error" | "info") => void;
  onSummaryChange: () => void;
  onNavigate: (module: AppModule, tab?: string, templateId?: string) => void;
}

const DOC_TYPES = ["Registration", "Title", "Insurance Card", "Inspection", "Other"];

function emptyForm(assets: CustomAsset[]): VehicleDocumentForm {
  return {
    asset_id: assets[0]?.id ?? 0,
    doc_type: DOC_TYPES[0],
    issued_date: "",
    expiry_date: "",
    notes: "",
  };
}

function docUrl(path: string | null) {
  if (!path) return null;
  return path.startsWith("/") ? `${API_BASE}${path}` : path;
}

function cleanPayload(form: VehicleDocumentForm): Record<string, unknown> {
  return {
    asset_id: form.asset_id,
    doc_type: form.doc_type,
    issued_date: form.issued_date || null,
    expiry_date: form.expiry_date || null,
    notes: form.notes || null,
  };
}

function isExpiringSoon(expiryDate: string | null): boolean {
  if (!expiryDate) return false;
  const today = new Date().toISOString().slice(0, 10);
  const cutoff = new Date(Date.now() + 60 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
  return expiryDate >= today && expiryDate <= cutoff;
}

function VehicleDocumentForm_({
  initial, assets, onSave, onCancel, saving,
}: {
  initial: VehicleDocumentForm;
  assets: CustomAsset[];
  onSave: (form: VehicleDocumentForm) => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const [form, setForm] = useState<VehicleDocumentForm>(initial);
  const set = (key: keyof VehicleDocumentForm, val: unknown) => setForm((f) => ({ ...f, [key]: val }));

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
          <label className="text-xs text-slate-500 mb-0.5 block">Document Type *</label>
          <select value={form.doc_type} onChange={(e) => set("doc_type", e.target.value)}
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400">
            {DOC_TYPES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-slate-500 mb-0.5 block">Issued Date</label>
          <input type="date" value={form.issued_date ?? ""} onChange={(e) => set("issued_date", e.target.value)}
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
        </div>
        <div>
          <label className="text-xs text-slate-500 mb-0.5 block">Expiry Date</label>
          <input type="date" value={form.expiry_date ?? ""} onChange={(e) => set("expiry_date", e.target.value)}
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
        </div>
      </div>
      <div>
        <label className="text-xs text-slate-500 mb-0.5 block">Notes</label>
        <textarea value={form.notes ?? ""} onChange={(e) => set("notes", e.target.value)} rows={2}
          className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
      </div>
      <div className="flex gap-2 pt-1">
        <button onClick={() => onSave(form)} disabled={saving || !form.asset_id || !form.doc_type}
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

export default function DocumentsTab({ assets, onToast, onSummaryChange, onNavigate }: Props) {
  const [documents, setDocuments] = useState<VehicleDocument[] | null>(null);
  const [showNewForm, setShowNewForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [uploadingId, setUploadingId] = useState<number | null>(null);

  useEffect(() => {
    api<VehicleDocument[]>("/vehicles/documents")
      .then(setDocuments)
      .catch(() => {
        onToast("Failed to load documents", "error");
        setDocuments([]);
      });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const createDocument = async (form: VehicleDocumentForm) => {
    setSaving(true);
    try {
      const created = await api<VehicleDocument>("/vehicles/documents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cleanPayload(form)),
      });
      setDocuments((prev) => [created, ...(prev ?? [])]);
      setShowNewForm(false);
      onSummaryChange();
      onToast("Document added", "success");
    } catch {
      onToast("Failed to add document", "error");
    } finally {
      setSaving(false);
    }
  };

  const updateDocument = async (id: number, form: VehicleDocumentForm) => {
    setSaving(true);
    try {
      const updated = await api<VehicleDocument>(`/vehicles/documents/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cleanPayload(form)),
      });
      setDocuments((prev) => (prev ?? []).map((d) => (d.id === id ? updated : d)));
      setEditingId(null);
      onSummaryChange();
      onToast("Document updated", "success");
    } catch {
      onToast("Failed to update document", "error");
    } finally {
      setSaving(false);
    }
  };

  const deleteDocument = async (id: number) => {
    if (!confirm("Delete this document record?")) return;
    try {
      await api(`/vehicles/documents/${id}`, { method: "DELETE" });
      setDocuments((prev) => (prev ?? []).filter((d) => d.id !== id));
      onSummaryChange();
      onToast("Document deleted", "success");
    } catch {
      onToast("Failed to delete document", "error");
    }
  };

  const uploadFile = async (id: number, file: File) => {
    setUploadingId(id);
    try {
      const token = await getAuthToken();
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`${API_BASE}/vehicles/documents/${id}/document`, {
        method: "POST",
        headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...orgHeader() },
        body: fd,
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const { document_url, document_filename } = await res.json();
      setDocuments((prev) => (prev ?? []).map((d) => (d.id === id ? { ...d, document_url, document_filename } : d)));
      onToast("File uploaded", "success");
    } catch {
      onToast("Failed to upload file", "error");
    } finally {
      setUploadingId(null);
    }
  };

  const documentToForm = (d: VehicleDocument): VehicleDocumentForm => ({
    asset_id: d.asset_id,
    doc_type: d.doc_type,
    issued_date: d.issued_date ?? "",
    expiry_date: d.expiry_date ?? "",
    notes: d.notes ?? "",
  });

  if (documents === null) {
    return <div className="py-16 text-center text-slate-400 text-sm">Loading…</div>;
  }

  if (assets.length === 0) {
    return (
      <div className="py-16 text-center text-slate-400 space-y-3">
        <div className="text-4xl">🚗</div>
        <div className="font-medium text-slate-600">No vehicles or bicycles yet</div>
        <p className="text-sm">Add one to your collection first, then come back to track documents.</p>
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
      {documents.length === 0 && !showNewForm && (
        <div className="py-16 text-center text-slate-400 space-y-2">
          <div className="text-4xl">📄</div>
          <div className="font-medium text-slate-600">No documents yet</div>
          <p className="text-sm">Track registration, title, insurance card, or inspection documents.</p>
        </div>
      )}

      {documents.map((document_) => {
        const isEditing = editingId === document_.id;
        const doc = docUrl(document_.document_url);
        const asset = assets.find((a) => a.id === document_.asset_id);
        const expiringSoon = isExpiringSoon(document_.expiry_date);
        return (
          <div key={document_.id} className="bg-white border border-slate-200 rounded-xl p-4 space-y-2">
            {isEditing ? (
              <VehicleDocumentForm_
                initial={documentToForm(document_)}
                assets={assets}
                onSave={(form) => updateDocument(document_.id, form)}
                onCancel={() => setEditingId(null)}
                saving={saving}
              />
            ) : (
              <>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="font-semibold text-slate-800">{document_.doc_type}</div>
                    <div className="flex gap-1.5 mt-1 flex-wrap text-xs">
                      {asset && <span className="bg-violet-50 text-violet-700 px-2 py-0.5 rounded-full">{asset.name}</span>}
                      {document_.issued_date && <span className="bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">issued {document_.issued_date}</span>}
                      {document_.expiry_date && (
                        <span className={`px-2 py-0.5 rounded-full ${expiringSoon ? "bg-amber-100 text-amber-700 font-medium" : "bg-slate-100 text-slate-600"}`}>
                          expires {document_.expiry_date}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <button onClick={() => setEditingId(document_.id)} className="text-slate-400 hover:text-indigo-600 p-1">
                      <Pencil className="w-4 h-4" />
                    </button>
                    <button onClick={() => deleteDocument(document_.id)} className="text-slate-400 hover:text-red-600 p-1">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {document_.notes && <p className="text-xs text-slate-500">{document_.notes}</p>}

                <div className="flex items-center justify-end pt-2 border-t border-slate-100 text-xs">
                  {doc && (
                    <a href={doc} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-indigo-600 hover:underline mr-2">
                      <ExternalLink className="w-3.5 h-3.5" />{document_.document_filename || "Document"}
                    </a>
                  )}
                  <label className="flex items-center gap-1 text-slate-500 hover:text-indigo-600 cursor-pointer">
                    <Paperclip className="w-3.5 h-3.5" />
                    {uploadingId === document_.id ? "Uploading…" : doc ? "Replace" : "Upload document"}
                    <input type="file" accept=".pdf,.jpg,.jpeg,.png,.webp" className="hidden"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) uploadFile(document_.id, file);
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
        <VehicleDocumentForm_ initial={emptyForm(assets)} assets={assets} onSave={createDocument} onCancel={() => setShowNewForm(false)} saving={saving} />
      ) : (
        <button onClick={() => setShowNewForm(true)}
          className="flex items-center gap-1.5 text-sm text-indigo-600 hover:text-indigo-800 font-medium">
          <Plus className="w-4 h-4" />Add Document
        </button>
      )}
    </div>
  );
}
