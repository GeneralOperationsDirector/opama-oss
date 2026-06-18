/** ******************************************************************
 * Storefront export key (per-org).
 *
 * The storefront site's pull (GET /assets/website-listings) and the Stripe sale
 * webhook (POST /assets/website-listings/{slug}/sold) authenticate with this
 * per-organization key, which scopes them to this org (pool tenancy). Owner-only:
 * the GET/POST /assets/website-listings/export-key endpoints 403 for non-owners,
 * so this section hides itself for them.
 ******************************************************************* */

import { useEffect, useState } from "react";
import { KeyRound, Copy, Check, RefreshCw, Eye, EyeOff } from "lucide-react";
import { api } from "../../lib/api";

type Props = {
  onToast: (msg: string, type?: "success" | "error" | "info") => void;
};

function mask(key: string): string {
  return "•".repeat(Math.max(0, key.length - 4)) + key.slice(-4);
}

export default function ExportKeySection({ onToast }: Props) {
  const [key, setKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [reveal, setReveal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let alive = true;
    api<{ export_key: string | null }>("/assets/website-listings/export-key")
      .then((r) => { if (alive) { setKey(r.export_key); setLoading(false); } })
      .catch((e) => {
        if (!alive) return;
        // Non-owners get 403 — just hide the whole section.
        if (/owner|403|forbidden/i.test(String(e?.message ?? e))) setForbidden(true);
        setLoading(false);
      });
    return () => { alive = false; };
  }, []);

  if (forbidden || loading) return null;

  const rotate = async () => {
    setBusy(true);
    try {
      const r = await api<{ export_key: string }>(
        "/assets/website-listings/export-key", { method: "POST" });
      setKey(r.export_key);
      setReveal(true);
      onToast(key ? "Export key rotated" : "Export key generated", "success");
    } catch {
      onToast("Could not update export key", "error");
    } finally {
      setBusy(false);
    }
  };

  const copy = async () => {
    if (!key) return;
    try {
      await navigator.clipboard.writeText(key);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      onToast("Copy failed — select and copy manually", "error");
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-slate-800">Storefront export key</h3>
        <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">
          Authenticates your storefront site pulling listings and posting sales
          back. Scoped to this organization — set it as <code className="font-mono bg-slate-100 text-slate-700 px-1 py-0.5 rounded text-[11px]">X-Export-Key</code> on your shop / Cloudflare Worker.
        </p>
      </div>

      {key ? (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <code className="flex-1 font-mono text-[12px] text-slate-700 bg-slate-100 border border-slate-200 rounded-lg px-2.5 py-2 truncate">
              {reveal ? key : mask(key)}
            </code>
            <button type="button" onClick={() => setReveal((v) => !v)} title={reveal ? "Hide" : "Reveal"}
              className="h-9 w-9 flex items-center justify-center rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-50">
              {reveal ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
            <button type="button" onClick={copy} title="Copy"
              className="h-9 w-9 flex items-center justify-center rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-50">
              {copied ? <Check className="w-4 h-4 text-emerald-600" /> : <Copy className="w-4 h-4" />}
            </button>
          </div>
          <button type="button" onClick={rotate} disabled={busy}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-amber-700 hover:text-amber-800 disabled:opacity-60">
            <RefreshCw className={`w-3.5 h-3.5 ${busy ? "animate-spin" : ""}`} />
            Rotate key
          </button>
          <p className="text-[11px] text-slate-400 leading-relaxed">
            Rotating immediately invalidates the old key — update your storefront site afterward.
          </p>
        </div>
      ) : (
        <button type="button" onClick={rotate} disabled={busy}
          className="inline-flex items-center gap-1.5 px-3 h-9 rounded-lg text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60">
          <KeyRound className="w-4 h-4" />
          {busy ? "Generating…" : "Generate export key"}
        </button>
      )}
    </div>
  );
}
