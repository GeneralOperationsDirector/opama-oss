/**
 * PoliciesTab — Insurance & Appraisals: Policies.
 *
 * Lists InsurancePolicy rows with create/edit/delete, document upload, and
 * an expandable "Scheduled Items" section per policy for itemized coverage
 * linked to CustomAsset rows (or free-text descriptions).
 */
import React, { useEffect, useState } from "react";
import { Plus, Pencil, Trash2, X, Check, ChevronDown, ChevronUp, Paperclip, ExternalLink } from "lucide-react";
import { api, API_BASE } from "../../lib/api";
import { getAuthToken } from "../../lib/authToken";
import type { CustomAsset } from "../custom-assets/types";
import type { InsurancePolicy, InsurancePolicyDetail, InsurancePolicyForm, PolicyItem } from "./types";

interface Props {
  assets: CustomAsset[];
  onToast: (msg: string, type?: "success" | "error" | "info") => void;
  onSummaryChange: () => void;
}

const EMPTY_FORM: InsurancePolicyForm = {
  provider: "",
  policy_number: "",
  policy_type: "",
  coverage_amount: null,
  deductible: null,
  premium_amount: null,
  premium_frequency: "",
  start_date: "",
  end_date: "",
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

// Converts empty-string optional fields to null before sending to the API.
function cleanPayload(form: InsurancePolicyForm): Record<string, unknown> {
  const out: Record<string, unknown> = { provider: form.provider };
  for (const [key, val] of Object.entries(form)) {
    if (key === "provider") continue;
    out[key] = val === "" ? null : val;
  }
  return out;
}

function PolicyForm({
  initial, onSave, onCancel, saving,
}: {
  initial: InsurancePolicyForm;
  onSave: (form: InsurancePolicyForm) => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const [form, setForm] = useState<InsurancePolicyForm>(initial);
  const set = (key: keyof InsurancePolicyForm, val: unknown) => setForm((f) => ({ ...f, [key]: val }));

  return (
    <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-slate-500 mb-0.5 block">Provider *</label>
          <input value={form.provider} onChange={(e) => set("provider", e.target.value)}
            placeholder="e.g. State Farm"
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
        </div>
        <div>
          <label className="text-xs text-slate-500 mb-0.5 block">Policy Number</label>
          <input value={form.policy_number ?? ""} onChange={(e) => set("policy_number", e.target.value)}
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-slate-500 mb-0.5 block">Policy Type</label>
          <input value={form.policy_type ?? ""} onChange={(e) => set("policy_type", e.target.value)}
            placeholder="e.g. Valuable items rider"
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
        </div>
        <div>
          <label className="text-xs text-slate-500 mb-0.5 block">Premium Frequency</label>
          <select value={form.premium_frequency ?? ""} onChange={(e) => set("premium_frequency", e.target.value)}
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400">
            <option value="">—</option>
            <option value="monthly">Monthly</option>
            <option value="annual">Annual</option>
          </select>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div>
          <label className="text-xs text-slate-500 mb-0.5 block">Coverage Amount</label>
          <input type="number" min={0} step="0.01" value={form.coverage_amount ?? ""}
            onChange={(e) => set("coverage_amount", e.target.value === "" ? null : parseFloat(e.target.value))}
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
        </div>
        <div>
          <label className="text-xs text-slate-500 mb-0.5 block">Deductible</label>
          <input type="number" min={0} step="0.01" value={form.deductible ?? ""}
            onChange={(e) => set("deductible", e.target.value === "" ? null : parseFloat(e.target.value))}
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
        </div>
        <div>
          <label className="text-xs text-slate-500 mb-0.5 block">Premium Amount</label>
          <input type="number" min={0} step="0.01" value={form.premium_amount ?? ""}
            onChange={(e) => set("premium_amount", e.target.value === "" ? null : parseFloat(e.target.value))}
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-slate-500 mb-0.5 block">Start Date</label>
          <input type="date" value={form.start_date ?? ""} onChange={(e) => set("start_date", e.target.value)}
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
        </div>
        <div>
          <label className="text-xs text-slate-500 mb-0.5 block">Renewal / End Date</label>
          <input type="date" value={form.end_date ?? ""} onChange={(e) => set("end_date", e.target.value)}
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
        </div>
      </div>
      <div>
        <label className="text-xs text-slate-500 mb-0.5 block">Notes</label>
        <textarea value={form.notes ?? ""} onChange={(e) => set("notes", e.target.value)} rows={2}
          className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
      </div>
      <div className="flex gap-2 pt-1">
        <button onClick={() => onSave(form)} disabled={saving || !form.provider.trim()}
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

function ItemsSection({
  policyId, assets, onToast, onSummaryChange,
}: {
  policyId: number;
  assets: CustomAsset[];
  onToast: Props["onToast"];
  onSummaryChange: () => void;
}) {
  const [items, setItems] = useState<PolicyItem[] | null>(null);
  const [adding, setAdding] = useState(false);
  const [assetId, setAssetId] = useState("");
  const [description, setDescription] = useState("");
  const [scheduledAmount, setScheduledAmount] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api<InsurancePolicyDetail>(`/insurance/policies/${policyId}`)
      .then((detail) => setItems(detail.items))
      .catch(() => onToast("Failed to load scheduled items", "error"));
  }, [policyId]); // eslint-disable-line react-hooks/exhaustive-deps

  const addItem = async () => {
    if (!description.trim()) {
      onToast("Description is required", "error");
      return;
    }
    setSaving(true);
    try {
      const item = await api<PolicyItem>(`/insurance/policies/${policyId}/items`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          asset_id: assetId ? parseInt(assetId, 10) : null,
          description: description.trim(),
          scheduled_amount: scheduledAmount === "" ? null : parseFloat(scheduledAmount),
        }),
      });
      setItems((prev) => [...(prev ?? []), item]);
      setAssetId("");
      setDescription("");
      setScheduledAmount("");
      setAdding(false);
      onSummaryChange();
      onToast("Item added", "success");
    } catch {
      onToast("Failed to add item", "error");
    } finally {
      setSaving(false);
    }
  };

  const removeItem = async (itemId: number) => {
    try {
      await api(`/insurance/policies/${policyId}/items/${itemId}`, { method: "DELETE" });
      setItems((prev) => (prev ?? []).filter((i) => i.id !== itemId));
      onSummaryChange();
      onToast("Item removed", "success");
    } catch {
      onToast("Failed to remove item", "error");
    }
  };

  return (
    <div className="space-y-2 pt-3 border-t border-slate-100">
      <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Scheduled Items</div>
      {items === null ? (
        <div className="text-xs text-slate-400">Loading…</div>
      ) : items.length === 0 && !adding ? (
        <div className="text-xs text-slate-400 italic">No scheduled items yet</div>
      ) : (
        <div className="space-y-1.5">
          {items?.map((item) => {
            const asset = assets.find((a) => a.id === item.asset_id);
            return (
              <div key={item.id} className="flex items-center justify-between gap-2 bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-sm">
                <div className="min-w-0">
                  <div className="text-slate-700 truncate">
                    {item.description}
                    {asset && <span className="text-slate-400 ml-1.5 text-xs">(linked: {asset.name})</span>}
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <span className="text-slate-500 text-xs">{fmtMoney(item.scheduled_amount)}</span>
                  <button onClick={() => removeItem(item.id)} className="text-slate-400 hover:text-red-600">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {adding ? (
        <div className="bg-white border border-slate-200 rounded-lg p-3 space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-slate-500 mb-0.5 block">Linked Asset (optional)</label>
              <select value={assetId} onChange={(e) => {
                const val = e.target.value;
                setAssetId(val);
                const asset = assets.find((a) => String(a.id) === val);
                if (asset && !description) setDescription(asset.name);
              }}
                className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400">
                <option value="">— none —</option>
                {assets.map((a) => (
                  <option key={a.id} value={a.id}>{a.name} ({a.category})</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-500 mb-0.5 block">Scheduled Amount</label>
              <input type="number" min={0} step="0.01" value={scheduledAmount}
                onChange={(e) => setScheduledAmount(e.target.value)}
                className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
            </div>
          </div>
          <div>
            <label className="text-xs text-slate-500 mb-0.5 block">Description *</label>
            <input value={description} onChange={(e) => setDescription(e.target.value)}
              placeholder="e.g. Charizard 1st Edition PSA 10"
              className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
          </div>
          <div className="flex gap-2">
            <button onClick={addItem} disabled={saving}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 text-white rounded-lg text-xs font-medium hover:bg-indigo-700 disabled:opacity-50">
              <Check className="w-3.5 h-3.5" />{saving ? "Adding…" : "Add"}
            </button>
            <button onClick={() => setAdding(false)} className="flex items-center gap-1.5 px-3 py-1.5 border border-slate-200 rounded-lg text-xs text-slate-600 hover:bg-slate-50">
              <X className="w-3.5 h-3.5" />Cancel
            </button>
          </div>
        </div>
      ) : (
        <button onClick={() => setAdding(true)}
          className="flex items-center gap-1.5 text-xs text-indigo-600 hover:text-indigo-800 font-medium">
          <Plus className="w-3.5 h-3.5" />Add item
        </button>
      )}
    </div>
  );
}

export default function PoliciesTab({ assets, onToast, onSummaryChange }: Props) {
  const [policies, setPolicies] = useState<InsurancePolicy[] | null>(null);
  const [showNewForm, setShowNewForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [uploadingId, setUploadingId] = useState<number | null>(null);

  useEffect(() => {
    api<InsurancePolicy[]>("/insurance/policies")
      .then(setPolicies)
      .catch(() => {
        onToast("Failed to load policies", "error");
        setPolicies([]);
      });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const createPolicy = async (form: InsurancePolicyForm) => {
    setSaving(true);
    try {
      const created = await api<InsurancePolicy>("/insurance/policies", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cleanPayload(form)),
      });
      setPolicies((prev) => [created, ...(prev ?? [])]);
      setShowNewForm(false);
      onSummaryChange();
      onToast("Policy added", "success");
    } catch {
      onToast("Failed to add policy", "error");
    } finally {
      setSaving(false);
    }
  };

  const updatePolicy = async (id: number, form: InsurancePolicyForm) => {
    setSaving(true);
    try {
      const updated = await api<InsurancePolicy>(`/insurance/policies/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cleanPayload(form)),
      });
      setPolicies((prev) => (prev ?? []).map((p) => (p.id === id ? updated : p)));
      setEditingId(null);
      onSummaryChange();
      onToast("Policy updated", "success");
    } catch {
      onToast("Failed to update policy", "error");
    } finally {
      setSaving(false);
    }
  };

  const deletePolicy = async (id: number) => {
    if (!confirm("Delete this policy and all its scheduled items?")) return;
    try {
      await api(`/insurance/policies/${id}`, { method: "DELETE" });
      setPolicies((prev) => (prev ?? []).filter((p) => p.id !== id));
      onSummaryChange();
      onToast("Policy deleted", "success");
    } catch {
      onToast("Failed to delete policy", "error");
    }
  };

  const uploadDocument = async (id: number, file: File) => {
    setUploadingId(id);
    try {
      const token = await getAuthToken();
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`${API_BASE}/insurance/policies/${id}/document`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: fd,
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const { document_url, document_filename } = await res.json();
      setPolicies((prev) => (prev ?? []).map((p) => (p.id === id ? { ...p, document_url, document_filename } : p)));
      onToast("Document uploaded", "success");
    } catch {
      onToast("Failed to upload document", "error");
    } finally {
      setUploadingId(null);
    }
  };

  const policyToForm = (p: InsurancePolicy): InsurancePolicyForm => ({
    provider: p.provider,
    policy_number: p.policy_number ?? "",
    policy_type: p.policy_type ?? "",
    coverage_amount: p.coverage_amount,
    deductible: p.deductible,
    premium_amount: p.premium_amount,
    premium_frequency: p.premium_frequency ?? "",
    start_date: p.start_date ?? "",
    end_date: p.end_date ?? "",
    notes: p.notes ?? "",
  });

  if (policies === null) {
    return <div className="py-16 text-center text-slate-400 text-sm">Loading…</div>;
  }

  return (
    <div className="space-y-3">
      {policies.length === 0 && !showNewForm && (
        <div className="py-16 text-center text-slate-400 space-y-2">
          <div className="text-4xl">🛡️</div>
          <div className="font-medium text-slate-600">No insurance policies yet</div>
          <p className="text-sm">Add a policy to track coverage and renewal dates.</p>
        </div>
      )}

      {policies.map((policy) => {
        const isEditing = editingId === policy.id;
        const isExpanded = expandedId === policy.id;
        const doc = docUrl(policy.document_url);
        return (
          <div key={policy.id} className="bg-white border border-slate-200 rounded-xl p-4 space-y-2">
            {isEditing ? (
              <PolicyForm
                initial={policyToForm(policy)}
                onSave={(form) => updatePolicy(policy.id, form)}
                onCancel={() => setEditingId(null)}
                saving={saving}
              />
            ) : (
              <>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="font-semibold text-slate-800">{policy.provider}</div>
                    <div className="flex gap-1.5 mt-1 flex-wrap text-xs">
                      {policy.policy_type && <span className="bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded-full">{policy.policy_type}</span>}
                      {policy.policy_number && <span className="bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full font-mono">#{policy.policy_number}</span>}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <button onClick={() => setEditingId(policy.id)} className="text-slate-400 hover:text-indigo-600 p-1">
                      <Pencil className="w-4 h-4" />
                    </button>
                    <button onClick={() => deletePolicy(policy.id)} className="text-slate-400 hover:text-red-600 p-1">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-1 text-xs text-slate-600">
                  <div><span className="text-slate-400">Coverage: </span>{fmtMoney(policy.coverage_amount)}</div>
                  <div><span className="text-slate-400">Deductible: </span>{fmtMoney(policy.deductible)}</div>
                  <div><span className="text-slate-400">Premium: </span>{fmtMoney(policy.premium_amount)}{policy.premium_frequency ? ` / ${policy.premium_frequency}` : ""}</div>
                  <div><span className="text-slate-400">Renews: </span>{policy.end_date || "—"}</div>
                </div>

                {policy.notes && <p className="text-xs text-slate-500">{policy.notes}</p>}

                <div className="flex items-center justify-between pt-2 border-t border-slate-100">
                  <button onClick={() => setExpandedId(isExpanded ? null : policy.id)}
                    className="flex items-center gap-1 text-xs text-slate-500 hover:text-indigo-600 font-medium">
                    {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                    Scheduled Items
                  </button>

                  <div className="flex items-center gap-2 text-xs">
                    {doc && (
                      <a href={doc} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-indigo-600 hover:underline">
                        <ExternalLink className="w-3.5 h-3.5" />{policy.document_filename || "Document"}
                      </a>
                    )}
                    <label className="flex items-center gap-1 text-slate-500 hover:text-indigo-600 cursor-pointer">
                      <Paperclip className="w-3.5 h-3.5" />
                      {uploadingId === policy.id ? "Uploading…" : doc ? "Replace" : "Upload document"}
                      <input type="file" accept=".pdf,.jpg,.jpeg,.png,.webp" className="hidden"
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (file) uploadDocument(policy.id, file);
                          e.target.value = "";
                        }} />
                    </label>
                  </div>
                </div>

                {isExpanded && (
                  <ItemsSection policyId={policy.id} assets={assets} onToast={onToast} onSummaryChange={onSummaryChange} />
                )}
              </>
            )}
          </div>
        );
      })}

      {showNewForm ? (
        <PolicyForm initial={EMPTY_FORM} onSave={createPolicy} onCancel={() => setShowNewForm(false)} saving={saving} />
      ) : (
        <button onClick={() => setShowNewForm(true)}
          className="flex items-center gap-1.5 text-sm text-indigo-600 hover:text-indigo-800 font-medium">
          <Plus className="w-4 h-4" />Add Policy
        </button>
      )}
    </div>
  );
}
