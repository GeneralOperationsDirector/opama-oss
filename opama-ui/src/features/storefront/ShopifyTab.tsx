import React, { useState } from "react";
import {
  Save, KeyRound, Eye, EyeOff, CheckCircle2, Store, Upload, RefreshCw,
  CheckCircle, AlertCircle, Clock, ExternalLink,
} from "lucide-react";
import { api } from "../../lib/api";
import type {
  ShopifySettings, ShopifyPublishPreview, ShopifyPublishResult, ShopifyTestResult,
} from "./types";

interface Props {
  settings: ShopifySettings | null;
  onSaved: (s: ShopifySettings) => void;
  onToast: (msg: string, type?: "success" | "error" | "info") => void;
}

const INPUT = "w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400";

export default function ShopifyTab({ settings, onSaved, onToast }: Props) {
  const [form, setForm] = useState({
    shop_domain:  settings?.shop_domain ?? "",
    access_token: "",   // always blank on load — existing token is preserved server-side
  });
  const [saving, setSaving] = useState(false);
  const [showToken, setShowToken] = useState(false);

  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<ShopifyTestResult | null>(null);

  const [previewing, setPreviewing] = useState(false);
  const [preview, setPreview] = useState<ShopifyPublishPreview | null>(null);

  const [publishing, setPublishing] = useState(false);
  const [publishResult, setPublishResult] = useState<ShopifyPublishResult | null>(null);

  const set = (k: keyof typeof form, v: string) => setForm(f => ({ ...f, [k]: v }));

  const isConfigured = !!(settings?.shop_domain && settings?.access_token_set);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setTestResult(null);
    try {
      const saved = await api<ShopifySettings>("/shopify/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          shop_domain:  form.shop_domain,
          access_token: form.access_token || null,  // null = keep existing
        }),
      });
      onSaved(saved);
      setForm(f => ({ ...f, access_token: "" }));
      onToast("Shopify settings saved", "success");
    } catch {
      onToast("Failed to save Shopify settings", "error");
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const data = await api<ShopifyTestResult>("/shopify/settings/test", { method: "POST" });
      setTestResult(data);
      if (data.connected) {
        onToast(`Connected to ${data.shop_name ?? data.domain}`, "success");
      } else {
        onToast("Could not connect to Shopify", "error");
      }
    } catch {
      onToast("Connection test failed", "error");
    } finally {
      setTesting(false);
    }
  };

  const handlePreview = async () => {
    setPreviewing(true);
    setPublishResult(null);
    try {
      const data = await api<ShopifyPublishPreview>("/shopify/publish/preview");
      setPreview(data);
    } catch {
      onToast("Failed to load preview", "error");
    } finally {
      setPreviewing(false);
    }
  };

  const handlePublish = async () => {
    if (!isConfigured) {
      onToast("Configure your shop domain and access token first", "error");
      return;
    }
    setPublishing(true);
    setPublishResult(null);
    try {
      const data = await api<ShopifyPublishResult>("/shopify/publish", { method: "POST" });
      setPublishResult(data);
      if (data.published) {
        onToast(
          `Synced to Shopify — ${data.created_count} created, ${data.updated_count} updated`,
          "success"
        );
        if (settings) {
          onSaved({ ...settings, last_published_at: new Date().toISOString() });
        }
      } else {
        onToast(data.error ?? "Shopify sync failed", "error");
      }
    } catch {
      onToast("Shopify publish request failed", "error");
    } finally {
      setPublishing(false);
    }
  };

  const productsToShow = publishResult ? undefined : preview?.products;

  return (
    <div className="space-y-8 max-w-2xl">
      {/* ── Settings ──────────────────────────────────────────────── */}
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <h3 className="text-sm font-semibold text-slate-800">Shopify Connection</h3>
          <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">
            Connect your Shopify store to publish your storefront catalog as products via the Admin API.
          </p>
        </div>

        <div className="space-y-1.5">
          <label className="block text-sm font-medium text-slate-700">
            Shop Domain <span className="ml-1 text-red-500">*</span>
          </label>
          <div className="relative">
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">
              <Store className="w-4 h-4" />
            </div>
            <input
              required
              value={form.shop_domain}
              onChange={e => set("shop_domain", e.target.value)}
              placeholder="yourshop.myshopify.com"
              className={`${INPUT} pl-9 font-mono`}
            />
          </div>
          <p className="text-xs text-slate-500 leading-relaxed">
            Your store's <code className="font-mono bg-slate-100 text-slate-700 px-1 py-0.5 rounded text-[11px]">myshopify.com</code> domain (not a custom domain).
          </p>
        </div>

        <div className="space-y-1.5">
          <label className="block text-sm font-medium text-slate-700">
            Admin API Access Token <span className="ml-1 text-red-500">*</span>
          </label>
          <div className="relative">
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">
              <KeyRound className="w-4 h-4" />
            </div>
            <input
              type={showToken ? "text" : "password"}
              value={form.access_token}
              onChange={e => set("access_token", e.target.value)}
              placeholder={settings?.access_token_set
                ? `Current token: ${settings.access_token_hint} — leave blank to keep`
                : "shpat_…"}
              className={`${INPUT} pl-9 pr-10 font-mono`}
            />
            <button
              type="button"
              onClick={() => setShowToken(v => !v)}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
            >
              {showToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
          {settings?.access_token_set && (
            <div className="flex items-center gap-1.5 text-xs text-emerald-700 mt-1">
              <CheckCircle2 className="w-3.5 h-3.5" />
              Token configured ({settings.access_token_hint}). Leave blank to keep it.
            </div>
          )}
          <p className="text-xs text-slate-500 leading-relaxed">
            Create a custom app in your Shopify admin (Settings → Apps and sales channels →
            Develop apps) with <code className="font-mono bg-slate-100 text-slate-700 px-1 py-0.5 rounded text-[11px]">write_products</code> and{" "}
            <code className="font-mono bg-slate-100 text-slate-700 px-1 py-0.5 rounded text-[11px]">read_products</code> scopes, then copy its Admin API access token here.
          </p>
        </div>

        <div className="flex gap-3 pt-1 border-t border-slate-100">
          <button
            type="submit"
            disabled={saving}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-medium disabled:opacity-50"
          >
            <Save className="w-4 h-4" />
            {saving ? "Saving…" : "Save Settings"}
          </button>
          <button
            type="button"
            onClick={handleTest}
            disabled={testing || !settings}
            className="flex items-center gap-2 px-4 py-2 border border-slate-200 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            <RefreshCw className="w-4 h-4" />
            {testing ? "Testing…" : "Test Connection"}
          </button>
        </div>

        {testResult && (
          <div className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-xs ${
            testResult.connected
              ? "bg-emerald-50 border-emerald-200 text-emerald-700"
              : "bg-red-50 border-red-200 text-red-700"
          }`}>
            {testResult.connected
              ? <CheckCircle className="w-3.5 h-3.5 flex-shrink-0" />
              : <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />}
            {testResult.connected
              ? <>Connected to <strong>{testResult.shop_name}</strong> ({testResult.domain})</>
              : "Could not connect — check your shop domain and access token."}
          </div>
        )}
      </form>

      {/* ── Publish ───────────────────────────────────────────────── */}
      <div className="space-y-4 pt-2 border-t border-slate-100">
        <div>
          <h3 className="text-sm font-semibold text-slate-800">Publish to Shopify</h3>
          <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">
            Syncs your active storefront listings to Shopify as products. Sold items are skipped.
          </p>
        </div>

        <div className="flex items-center gap-2 text-xs text-slate-500">
          <Clock className="w-3.5 h-3.5" />
          {settings?.last_published_at
            ? <>Last synced: {new Date(settings.last_published_at).toLocaleString()}</>
            : "Never synced"}
        </div>

        {!isConfigured && (
          <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2.5 text-xs text-amber-700">
            <AlertCircle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
            Configure your shop domain and access token above to enable syncing.
          </div>
        )}

        <div className="flex flex-wrap gap-3">
          <button
            onClick={handlePreview}
            disabled={previewing}
            className="flex items-center gap-2 px-4 py-2 border border-slate-200 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            <Eye className="w-4 h-4" />
            {previewing ? "Loading…" : "Preview Products"}
          </button>
          <button
            onClick={handlePublish}
            disabled={publishing || !isConfigured}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-medium disabled:opacity-50"
          >
            <Upload className="w-4 h-4" />
            {publishing ? "Syncing…" : "Sync to Shopify"}
          </button>
        </div>

        {/* Publish result */}
        {publishResult && (
          <div className={`flex items-start gap-3 p-4 rounded-xl border text-sm ${
            publishResult.published
              ? "bg-emerald-50 border-emerald-200 text-emerald-800"
              : "bg-red-50 border-red-200 text-red-800"
          }`}>
            {publishResult.published
              ? <CheckCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
              : <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />}
            <div className="space-y-1.5">
              {publishResult.published
                ? (
                  <div>
                    <strong>Synced successfully.</strong>{" "}
                    {publishResult.created_count} created, {publishResult.updated_count} updated, {publishResult.skipped_count} skipped.
                  </div>
                ) : (
                  <div><strong>Sync failed.</strong> {publishResult.error}</div>
                )}
              {publishResult.errors.length > 0 && (
                <ul className="list-disc list-inside text-xs space-y-0.5">
                  {publishResult.errors.map((err, i) => <li key={i}>{err}</li>)}
                </ul>
              )}
            </div>
          </div>
        )}

        {/* Preview */}
        {preview && (
          <div className="space-y-3">
            <div className="text-sm font-semibold text-slate-700">
              Preview — {preview.item_count} products
              {preview.skipped_sold_count > 0 && <> ({preview.skipped_sold_count} sold items skipped)</>}
            </div>
            <div className="space-y-2">
              {(productsToShow ?? preview.products).map((product, i) => (
                <div key={i} className="flex items-center gap-3 bg-white border border-slate-200 rounded-lg px-3 py-2 text-sm">
                  {product.images[0] ? (
                    <img src={product.images[0].src} alt={product.title} className="w-8 h-10 object-cover rounded flex-shrink-0" />
                  ) : (
                    <div className="w-8 h-10 bg-slate-100 rounded flex-shrink-0" />
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-slate-800 truncate">{product.title}</div>
                    <div className="text-xs text-slate-400">{product.product_type}</div>
                  </div>
                  <div className="flex flex-col items-end text-xs flex-shrink-0">
                    <span className="font-medium">${product.variants[0]?.price ?? "0.00"}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {settings?.shop_domain && (
          <a
            href={`https://${settings.shop_domain}/admin/products`}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-xs text-indigo-600 hover:underline"
          >
            <ExternalLink className="w-3 h-3" /> View products in Shopify admin
          </a>
        )}
      </div>
    </div>
  );
}
