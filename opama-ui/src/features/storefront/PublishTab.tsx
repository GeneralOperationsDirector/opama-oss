import React, { useState } from "react";
import { Upload, Eye, CheckCircle, AlertCircle, Clock, Download, GitCommit, ExternalLink } from "lucide-react";
import { api } from "../../lib/api";
import type { StorefrontSettings, PublishResult, CatalogEntry } from "./types";

interface Props {
  settings: StorefrontSettings | null;
  onToast: (msg: string, type?: "success" | "error" | "info") => void;
  onSettingsUpdated: (s: StorefrontSettings) => void;
}

export default function PublishTab({ settings, onToast, onSettingsUpdated }: Props) {
  const [publishing, setPublishing] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [result, setResult] = useState<PublishResult | null>(null);
  const [preview, setPreview] = useState<{ item_count: number; sold_count: number; catalog: CatalogEntry[] } | null>(null);
  const [showJson, setShowJson] = useState(false);

  const isConfigured = settings && (settings.catalog_path || settings.webhook_url);

  const handlePreview = async () => {
    setPreviewing(true);
    setResult(null);
    try {
      const data = await api<typeof preview>("/storefront/publish/preview");
      setPreview(data);
    } catch {
      onToast("Failed to load preview", "error");
    } finally {
      setPreviewing(false);
    }
  };

  const handlePublish = async () => {
    if (!isConfigured) {
      onToast("Configure a catalog path or webhook URL in Settings first", "error");
      return;
    }
    setPublishing(true);
    setResult(null);
    try {
      const data = await api<PublishResult>("/storefront/publish", { method: "POST" });
      setResult(data);
      if (data.published) {
        onToast(`Published ${data.item_count} items to ${settings?.site_name}`, "success");
        if (settings && data.last_published_at) {
          onSettingsUpdated({ ...settings, last_published_at: data.last_published_at });
        }
      } else {
        onToast(data.error ?? "Publish failed", "error");
      }
    } catch {
      onToast("Publish request failed", "error");
    } finally {
      setPublishing(false);
    }
  };

  const downloadCatalog = (catalog: CatalogEntry[]) => {
    const blob = new Blob([JSON.stringify(catalog, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "catalog.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  const catalogToShow = result?.catalog ?? preview?.catalog;
  const countToShow = result?.item_count ?? preview?.item_count;
  const soldToShow = result?.sold_count ?? preview?.sold_count;

  return (
    <div className="space-y-6 max-w-2xl">
      {/* Status bar */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="text-sm font-semibold text-slate-700">
            {settings?.site_name || "Shop"}
          </div>
          {settings?.site_url && (
            <a href={settings.site_url} target="_blank" rel="noreferrer"
              className="text-xs text-indigo-600 hover:underline">
              Visit →
            </a>
          )}
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <Clock className="w-3.5 h-3.5" />
          {settings?.last_published_at
            ? <>Last published: {new Date(settings.last_published_at).toLocaleString()}</>
            : "Never published"}
        </div>
        {!isConfigured && (
          <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-xs text-amber-700">
            <AlertCircle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
            No publish target configured. Go to Settings and set a Catalog File Path or Webhook URL.
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex flex-wrap gap-3">
        <button
          onClick={handlePreview}
          disabled={previewing}
          className="flex items-center gap-2 px-4 py-2 border border-slate-200 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          <Eye className="w-4 h-4" />
          {previewing ? "Loading…" : "Preview Catalog"}
        </button>
        <button
          onClick={handlePublish}
          disabled={publishing || !isConfigured}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-medium disabled:opacity-50"
        >
          <Upload className="w-4 h-4" />
          {publishing ? "Publishing…" : `Publish to ${settings?.site_name || "Shop"}`}
        </button>
      </div>

      {/* Result banner */}
      {result && (
        <div className={`flex items-start gap-3 p-4 rounded-xl border text-sm ${
          result.published
            ? "bg-emerald-50 border-emerald-200 text-emerald-800"
            : "bg-red-50 border-red-200 text-red-800"
        }`}>
          {result.published
            ? <CheckCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
            : <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />}
          <div className="space-y-1.5">
            {result.published
              ? <div><strong>Published successfully.</strong> {result.item_count} items ({result.sold_count} sold).</div>
              : <div><strong>Publish failed.</strong> {result.error}</div>}
            {result.github_commit_url && (
              <a
                href={result.github_commit_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-700 hover:text-emerald-900 hover:underline"
              >
                <GitCommit className="w-3.5 h-3.5" />
                View commit on GitHub
                <ExternalLink className="w-3 h-3" />
              </a>
            )}
            {result.published && result.github_commit_url && (
              <p className="text-xs text-emerald-600">
                Cloudflare Pages will deploy automatically within ~60 seconds.
              </p>
            )}
          </div>
        </div>
      )}

      {/* Catalog preview */}
      {catalogToShow && catalogToShow.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="text-sm font-semibold text-slate-700">
              Catalog Preview — {countToShow} items, {soldToShow} sold
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setShowJson(!showJson)}
                className="text-xs text-indigo-600 hover:underline"
              >
                {showJson ? "Hide JSON" : "View JSON"}
              </button>
              <button
                onClick={() => downloadCatalog(catalogToShow)}
                className="flex items-center gap-1 text-xs text-slate-600 hover:text-indigo-600"
              >
                <Download className="w-3.5 h-3.5" /> Download
              </button>
            </div>
          </div>

          {showJson ? (
            <pre className="bg-slate-900 text-slate-100 rounded-xl p-4 text-xs overflow-auto max-h-96 scrollbar-thin">
              {JSON.stringify(catalogToShow, null, 2)}
            </pre>
          ) : (
            <div className="space-y-2">
              {catalogToShow.map(entry => (
                <div key={entry.id} className={`flex items-center gap-3 bg-white border rounded-lg px-3 py-2 text-sm ${entry.sold ? "opacity-50" : ""}`}>
                  {entry.images[0] ? (
                    <img src={entry.images[0]} alt={entry.title} className="w-8 h-10 object-cover rounded flex-shrink-0" />
                  ) : (
                    <div className="w-8 h-10 bg-slate-100 rounded flex-shrink-0" />
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-slate-800 truncate">{entry.title}</div>
                    <div className="text-xs text-slate-400">{entry.category} · {entry.condition}</div>
                  </div>
                  <div className="flex flex-col items-end text-xs flex-shrink-0">
                    <span className="font-medium">${entry.priceCad.toFixed(2)}</span>
                    {entry.sold && <span className="text-red-500 font-medium">SOLD</span>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
