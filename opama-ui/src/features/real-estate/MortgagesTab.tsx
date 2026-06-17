/**
 * MortgagesTab — Property Records: Mortgages.
 *
 * Lists MortgageLoan rows (lender, terms, user-maintained current balance)
 * for the user's "Real Estate" category assets, with create/edit/delete and
 * document upload. If the user has no real-estate assets yet, shows a hint.
 */
import React, { useEffect, useState } from "react";
import { Plus, Pencil, Trash2, X, Check, Paperclip, ExternalLink } from "lucide-react";
import { api, API_BASE } from "../../lib/api";
import { getAuthToken } from "../../lib/authToken";
import { orgHeader } from "../../lib/activeOrg";
import type { CustomAsset } from "../custom-assets/types";
import type { MortgageLoan, MortgageLoanForm } from "./types";

interface Props {
  assets: CustomAsset[];
  onToast: (msg: string, type?: "success" | "error" | "info") => void;
  onSummaryChange: () => void;
}

function emptyForm(assets: CustomAsset[]): MortgageLoanForm {
  return {
    asset_id: assets[0]?.id ?? 0,
    lender: "",
    loan_number: "",
    original_amount: null,
    interest_rate: null,
    term_months: null,
    monthly_payment: null,
    start_date: "",
    current_balance: null,
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

function cleanPayload(form: MortgageLoanForm): Record<string, unknown> {
  return {
    asset_id: form.asset_id,
    lender: form.lender,
    loan_number: form.loan_number || null,
    original_amount: form.original_amount,
    interest_rate: form.interest_rate,
    term_months: form.term_months,
    monthly_payment: form.monthly_payment,
    start_date: form.start_date || null,
    current_balance: form.current_balance,
    notes: form.notes || null,
  };
}

function MortgageLoanForm_({
  initial, assets, onSave, onCancel, saving,
}: {
  initial: MortgageLoanForm;
  assets: CustomAsset[];
  onSave: (form: MortgageLoanForm) => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const [form, setForm] = useState<MortgageLoanForm>(initial);
  const set = (key: keyof MortgageLoanForm, val: unknown) => setForm((f) => ({ ...f, [key]: val }));

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
          <label className="text-xs text-slate-500 mb-0.5 block">Lender *</label>
          <input value={form.lender} onChange={(e) => set("lender", e.target.value)}
            placeholder="e.g. Wells Fargo"
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-slate-500 mb-0.5 block">Loan Number</label>
          <input value={form.loan_number ?? ""} onChange={(e) => set("loan_number", e.target.value)}
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
        </div>
        <div>
          <label className="text-xs text-slate-500 mb-0.5 block">Start Date</label>
          <input type="date" value={form.start_date ?? ""} onChange={(e) => set("start_date", e.target.value)}
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
        </div>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div>
          <label className="text-xs text-slate-500 mb-0.5 block">Original Amount</label>
          <input type="number" min={0} step="0.01" value={form.original_amount ?? ""}
            onChange={(e) => set("original_amount", e.target.value === "" ? null : parseFloat(e.target.value))}
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
        </div>
        <div>
          <label className="text-xs text-slate-500 mb-0.5 block">Interest Rate (%)</label>
          <input type="number" min={0} step="0.001" value={form.interest_rate ?? ""}
            onChange={(e) => set("interest_rate", e.target.value === "" ? null : parseFloat(e.target.value))}
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
        </div>
        <div>
          <label className="text-xs text-slate-500 mb-0.5 block">Term (months)</label>
          <input type="number" min={0} value={form.term_months ?? ""}
            onChange={(e) => set("term_months", e.target.value === "" ? null : parseInt(e.target.value, 10))}
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-slate-500 mb-0.5 block">Monthly Payment</label>
          <input type="number" min={0} step="0.01" value={form.monthly_payment ?? ""}
            onChange={(e) => set("monthly_payment", e.target.value === "" ? null : parseFloat(e.target.value))}
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
        </div>
        <div>
          <label className="text-xs text-slate-500 mb-0.5 block">Current Balance</label>
          <input type="number" min={0} step="0.01" value={form.current_balance ?? ""}
            onChange={(e) => set("current_balance", e.target.value === "" ? null : parseFloat(e.target.value))}
            className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
        </div>
      </div>
      <div>
        <label className="text-xs text-slate-500 mb-0.5 block">Notes</label>
        <textarea value={form.notes ?? ""} onChange={(e) => set("notes", e.target.value)} rows={2}
          className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
      </div>
      <div className="flex gap-2 pt-1">
        <button onClick={() => onSave(form)} disabled={saving || !form.asset_id || !form.lender.trim()}
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

export default function MortgagesTab({ assets, onToast, onSummaryChange }: Props) {
  const [loans, setLoans] = useState<MortgageLoan[] | null>(null);
  const [showNewForm, setShowNewForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [uploadingId, setUploadingId] = useState<number | null>(null);

  useEffect(() => {
    api<MortgageLoan[]>("/real-estate/mortgages")
      .then(setLoans)
      .catch(() => {
        onToast("Failed to load mortgages", "error");
        setLoans([]);
      });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const createLoan = async (form: MortgageLoanForm) => {
    setSaving(true);
    try {
      const created = await api<MortgageLoan>("/real-estate/mortgages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cleanPayload(form)),
      });
      setLoans((prev) => [created, ...(prev ?? [])]);
      setShowNewForm(false);
      onSummaryChange();
      onToast("Mortgage added", "success");
    } catch {
      onToast("Failed to add mortgage", "error");
    } finally {
      setSaving(false);
    }
  };

  const updateLoan = async (id: number, form: MortgageLoanForm) => {
    setSaving(true);
    try {
      const updated = await api<MortgageLoan>(`/real-estate/mortgages/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cleanPayload(form)),
      });
      setLoans((prev) => (prev ?? []).map((l) => (l.id === id ? updated : l)));
      setEditingId(null);
      onSummaryChange();
      onToast("Mortgage updated", "success");
    } catch {
      onToast("Failed to update mortgage", "error");
    } finally {
      setSaving(false);
    }
  };

  const deleteLoan = async (id: number) => {
    if (!confirm("Delete this mortgage record?")) return;
    try {
      await api(`/real-estate/mortgages/${id}`, { method: "DELETE" });
      setLoans((prev) => (prev ?? []).filter((l) => l.id !== id));
      onSummaryChange();
      onToast("Mortgage deleted", "success");
    } catch {
      onToast("Failed to delete mortgage", "error");
    }
  };

  const uploadDocument = async (id: number, file: File) => {
    setUploadingId(id);
    try {
      const token = await getAuthToken();
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`${API_BASE}/real-estate/mortgages/${id}/document`, {
        method: "POST",
        headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...orgHeader() },
        body: fd,
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const { document_url, document_filename } = await res.json();
      setLoans((prev) => (prev ?? []).map((l) => (l.id === id ? { ...l, document_url, document_filename } : l)));
      onToast("Document uploaded", "success");
    } catch {
      onToast("Failed to upload document", "error");
    } finally {
      setUploadingId(null);
    }
  };

  const loanToForm = (l: MortgageLoan): MortgageLoanForm => ({
    asset_id: l.asset_id,
    lender: l.lender,
    loan_number: l.loan_number ?? "",
    original_amount: l.original_amount,
    interest_rate: l.interest_rate,
    term_months: l.term_months,
    monthly_payment: l.monthly_payment,
    start_date: l.start_date ?? "",
    current_balance: l.current_balance,
    notes: l.notes ?? "",
  });

  if (loans === null) {
    return <div className="py-16 text-center text-slate-400 text-sm">Loading…</div>;
  }

  if (assets.length === 0) {
    return (
      <div className="py-16 text-center text-slate-400 space-y-2">
        <div className="text-4xl">🏠</div>
        <div className="font-medium text-slate-600">No properties yet</div>
        <p className="text-sm">Add a property in Collections first, then come back to track mortgages.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {loans.length === 0 && !showNewForm && (
        <div className="py-16 text-center text-slate-400 space-y-2">
          <div className="text-4xl">🏦</div>
          <div className="font-medium text-slate-600">No mortgages yet</div>
          <p className="text-sm">Add a mortgage to track lender, terms, and balance.</p>
        </div>
      )}

      {loans.map((loan) => {
        const isEditing = editingId === loan.id;
        const doc = docUrl(loan.document_url);
        const asset = assets.find((a) => a.id === loan.asset_id);
        return (
          <div key={loan.id} className="bg-white border border-slate-200 rounded-xl p-4 space-y-2">
            {isEditing ? (
              <MortgageLoanForm_
                initial={loanToForm(loan)}
                assets={assets}
                onSave={(form) => updateLoan(loan.id, form)}
                onCancel={() => setEditingId(null)}
                saving={saving}
              />
            ) : (
              <>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="font-semibold text-slate-800">{loan.lender}</div>
                    <div className="flex gap-1.5 mt-1 flex-wrap text-xs">
                      {asset && <span className="bg-violet-50 text-violet-700 px-2 py-0.5 rounded-full">{asset.name}</span>}
                      {loan.loan_number && <span className="bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full font-mono">#{loan.loan_number}</span>}
                      {loan.interest_rate != null && <span className="bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">{loan.interest_rate}%</span>}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <button onClick={() => setEditingId(loan.id)} className="text-slate-400 hover:text-indigo-600 p-1">
                      <Pencil className="w-4 h-4" />
                    </button>
                    <button onClick={() => deleteLoan(loan.id)} className="text-slate-400 hover:text-red-600 p-1">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-1 text-xs text-slate-600">
                  <div><span className="text-slate-400">Original: </span>{fmtMoney(loan.original_amount)}</div>
                  <div><span className="text-slate-400">Balance: </span>{fmtMoney(loan.current_balance)}</div>
                  <div><span className="text-slate-400">Payment: </span>{fmtMoney(loan.monthly_payment)}/mo</div>
                  <div><span className="text-slate-400">Term: </span>{loan.term_months ? `${loan.term_months} mo` : "—"}</div>
                </div>

                {loan.notes && <p className="text-xs text-slate-500">{loan.notes}</p>}

                <div className="flex items-center justify-end pt-2 border-t border-slate-100 text-xs">
                  {doc && (
                    <a href={doc} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-indigo-600 hover:underline mr-2">
                      <ExternalLink className="w-3.5 h-3.5" />{loan.document_filename || "Document"}
                    </a>
                  )}
                  <label className="flex items-center gap-1 text-slate-500 hover:text-indigo-600 cursor-pointer">
                    <Paperclip className="w-3.5 h-3.5" />
                    {uploadingId === loan.id ? "Uploading…" : doc ? "Replace" : "Upload document"}
                    <input type="file" accept=".pdf,.jpg,.jpeg,.png,.webp" className="hidden"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) uploadDocument(loan.id, file);
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
        <MortgageLoanForm_ initial={emptyForm(assets)} assets={assets} onSave={createLoan} onCancel={() => setShowNewForm(false)} saving={saving} />
      ) : (
        <button onClick={() => setShowNewForm(true)}
          className="flex items-center gap-1.5 text-sm text-indigo-600 hover:text-indigo-800 font-medium">
          <Plus className="w-4 h-4" />Add Mortgage
        </button>
      )}
    </div>
  );
}
