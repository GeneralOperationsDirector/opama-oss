/**
 * StorefrontModule — container for the four Storefront tabs.
 *
 * Tab shell over Listings / Sales / Publish / Settings (each its own file).
 * Owns the shared settings + listings + sales fetch and hands slices to the
 * tabs. Backend: services/storefront — the Publish tab pushes a catalog.json
 * to GitHub/file/webhook; Sales is populated by the Stripe sale webhook.
 */
import React, { useCallback, useEffect, useState } from "react";
import { Tag, DollarSign, Upload, Settings, ShoppingBag } from "lucide-react";
import { api } from "../../lib/api";
import { isModuleEnabled } from "../../lib/moduleRegistry";
import type { StorefrontSettings, StorefrontListing, SalesData, ShopifySettings } from "./types";
import ListingsTab from "./ListingsTab";
import SalesTab from "./SalesTab";
import PublishTab from "./PublishTab";
import SettingsTab from "./SettingsTab";
import ShopifyTab from "./ShopifyTab";

interface Props {
  userId: number;
  onToast: (msg: string, type?: "success" | "error" | "info") => void;
}

type Tab = "listings" | "sales" | "publish" | "settings" | "shopify";

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: "listings", label: "Listings",  icon: <Tag className="w-4 h-4" />      },
  { id: "sales",    label: "Sales",     icon: <DollarSign className="w-4 h-4" />},
  { id: "publish",  label: "Publish",   icon: <Upload className="w-4 h-4" />   },
  { id: "settings", label: "Settings",  icon: <Settings className="w-4 h-4" /> },
  ...(isModuleEnabled("shopify")
    ? [{ id: "shopify" as Tab, label: "Shopify", icon: <ShoppingBag className="w-4 h-4" /> }]
    : []),
];

export default function StorefrontModule({ userId, onToast }: Props) {
  const [tab, setTab] = useState<Tab>("listings");
  const [settings, setSettings] = useState<StorefrontSettings | null>(null);
  const [settingsLoaded, setSettingsLoaded] = useState(false);
  const [listings, setListings] = useState<StorefrontListing[]>([]);
  const [sales, setSales] = useState<SalesData | null>(null);
  const [loading, setLoading] = useState(true);
  const [shopifySettings, setShopifySettings] = useState<ShopifySettings | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [listData, salesData] = await Promise.all([
        api<StorefrontListing[]>("/storefront/listings"),
        api<SalesData>("/storefront/sales"),
      ]);
      setListings(listData);
      setSales(salesData);
    } catch {
      onToast("Failed to load storefront data", "error");
    } finally {
      setLoading(false);
    }
  }, [onToast]);

  const loadSettings = useCallback(async () => {
    try {
      const s = await api<StorefrontSettings>("/storefront/settings");
      setSettings(s);
    } catch {
      setSettings(null);
    } finally {
      setSettingsLoaded(true);
    }
  }, []);

  const loadShopifySettings = useCallback(async () => {
    try {
      const s = await api<ShopifySettings>("/shopify/settings");
      setShopifySettings(s);
    } catch {
      setShopifySettings(null);
    }
  }, []);

  useEffect(() => {
    load();
    loadSettings();
    if (isModuleEnabled("shopify")) {
      loadShopifySettings();
    }
  }, [load, loadSettings, loadShopifySettings]);

  const handleListingUpdated = (updated: StorefrontListing) => {
    setListings(prev => prev.map(l => l.id === updated.id ? { ...l, ...updated } : l));
  };

  const isConfigured = settings && (settings.catalog_path || settings.webhook_url);

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
            🛒 {settings?.site_name || "Storefront"}
          </h2>
          {settings?.site_url && (
            <a href={settings.site_url} target="_blank" rel="noreferrer"
              className="text-xs text-indigo-600 hover:underline mt-0.5 block">
              {settings.site_url} →
            </a>
          )}
        </div>
        {!loading && (
          <div className="flex items-center gap-3 text-sm text-slate-500">
            <span><strong className="text-slate-700">{listings.filter(l => !l.sale_date).length}</strong> listed</span>
            <span><strong className="text-slate-700">{listings.filter(l => !!l.sale_date).length}</strong> sold</span>
          </div>
        )}
      </div>

      {/* First-time setup prompt */}
      {settingsLoaded && !isConfigured && tab !== "settings" && (
        <div className="bg-indigo-50 border border-indigo-200 rounded-xl px-4 py-3 flex items-center justify-between gap-3 text-sm">
          <span className="text-indigo-700">Configure your shop's name, URL, and publish target to get started.</span>
          <button onClick={() => setTab("settings")} className="px-3 py-1.5 bg-indigo-600 text-white rounded-lg text-xs font-medium hover:bg-indigo-700 flex-shrink-0">
            Open Settings
          </button>
        </div>
      )}

      {/* Tab strip */}
      <div className="flex gap-1 border-b border-slate-200">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === t.id
                ? "border-indigo-600 text-indigo-600"
                : "border-transparent text-slate-500 hover:text-slate-800 hover:border-slate-300"
            }`}
          >
            {t.icon}
            {t.label}
            {t.id === "listings" && listings.filter(l => !l.sale_date).length > 0 && (
              <span className="ml-1 bg-indigo-100 text-indigo-700 text-xs px-1.5 py-0.5 rounded-full font-medium">
                {listings.filter(l => !l.sale_date).length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div>
        {loading && tab !== "settings" ? (
          <div className="py-16 text-center text-slate-400 text-sm">Loading…</div>
        ) : tab === "listings" ? (
          <ListingsTab listings={listings} onUpdated={handleListingUpdated} onToast={onToast} />
        ) : tab === "sales" ? (
          <SalesTab data={sales} />
        ) : tab === "publish" ? (
          <PublishTab settings={settings} onToast={onToast} onSettingsUpdated={setSettings} />
        ) : tab === "shopify" ? (
          <ShopifyTab settings={shopifySettings} onSaved={setShopifySettings} onToast={onToast} />
        ) : (
          <SettingsTab settings={settings} onSaved={setSettings} onToast={onToast} />
        )}
      </div>
    </div>
  );
}
