/**
 * eBay Tab
 * --------
 * Two modes:
 *  1) API mode (VITE_USE_EBAY_API=1): calls your backend /api/ebay/search
 *  2) Affiliate mode (default): opens eBay search with your affiliate code
 *
 * UX upgrades:
 * - Non-blocking toasts instead of alert()
 * - Sync input with `initialQuery` (from OpamaApp) and auto-search (API mode)
 * - Cancels in-flight requests to prevent racey results on rapid searches
 * - Graceful fallback: 404 from /api/ebay/search → open affiliate automatically
 */

import React, { useEffect, useRef, useState } from "react";
import { epnSearchUrl } from "../../lib/epn"; // adjust if your epn.ts path differs
import Button from "../../shared/atoms/Button";
import TextInput from "../../shared/atoms/TextInput";
import Section from "../../shared/atoms/Section";
import { useToast } from "../../shared/Toaster";

const API_BASE = (import.meta.env as any).VITE_API_BASE ?? "http://localhost:8008";
const USE_EBAY_API = ((import.meta.env as any).VITE_USE_EBAY_API ?? "0") === "1";

type EbayItem = {
  item_id: string;
  title: string;
  price?: string | null;
  currency?: string | null;
  image?: string | null;
  item_web_url?: string | null;
  affiliate_url?: string | null;
};

type EbaySearchResp = {
  total: number;
  items: EbayItem[];
};

export default function EbayTab({ initialQuery = "" }: { initialQuery?: string }) {
  const { toast, error: toastError } = useToast();

  const [q, setQ] = useState(initialQuery);
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<EbayItem[]>([]);
  const apiEnabled = USE_EBAY_API;

  // keep an AbortController for the current request to cancel when a new search starts
  const abortRef = useRef<AbortController | null>(null);

  function openAffiliate() {
    const query = (q || "Pokemon TCG").trim();
    const url = epnSearchUrl(query);
    window.open(url, "_blank", "noopener,noreferrer");
    toast(`Opened eBay for “${query}”`, { title: "Affiliate search" });
  }

  async function apiSearch() {
    // cancel any in-flight search
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    setLoading(true);
    setItems([]);

    try {
      const res = await fetch(`${API_BASE}/api/ebay/search`, {
        method: "POST", // keep POST to match your existing backend
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ q, limit: 24, offset: 0 }),
        signal: ac.signal,
      });

      // Seamless fallback if the backend route isn't wired up
      if (res.status === 404) {
        openAffiliate();
        return;
      }
      if (!res.ok) throw new Error(`ebay/search failed: ${res.status}`);

      const data: EbaySearchResp = await res.json();
      setItems(Array.isArray(data.items) ? data.items : []);
    } catch (e: any) {
      if (e?.name === "AbortError") return; // quietly ignore canceled requests
      toastError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }

  // Keep the input in sync if parent changes `initialQuery` (e.g., deep-link from a card action)
  useEffect(() => {
    setQ(initialQuery);
    if (initialQuery && apiEnabled) {
      // auto-search on prefill in API mode
      apiSearch();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialQuery, apiEnabled]);

  return (
    <Section
      title="eBay Search"
      subtitle={apiEnabled ? "Live results via your server’s eBay proxy" : "Developer API not configured — using affiliate search"}
    >
      <div className="flex gap-2">
        <TextInput
          placeholder="Search eBay for a card (e.g., Charizard sv3)"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") (apiEnabled ? apiSearch : openAffiliate)();
          }}
        />
        <Button onClick={apiEnabled ? apiSearch : openAffiliate} loading={loading}>
          {apiEnabled ? "Search" : "Open on eBay"}
        </Button>
      </div>

      {apiEnabled ? (
        <>
          {loading && <div className="mt-3 text-sm text-slate-600">Loading…</div>}

          <div className="mt-4 grid md:grid-cols-2 lg:grid-cols-3 gap-4">
            {items.map((it) => (
              <article key={it.item_id} className="rounded-2xl border p-3 shadow-sm">
                <div className="aspect-[4/3] w-full rounded-xl border bg-white grid place-items-center overflow-hidden">
                  {it.image ? (
                    <img
                      src={it.image}
                      alt={it.title}
                      className="w-full h-full object-contain"
                      loading="lazy"
                      decoding="async"
                    />
                  ) : (
                    <div className="text-xs text-slate-500">No image</div>
                  )}
                </div>

                <h3 className="mt-2 font-semibold line-clamp-2">{it.title}</h3>
                <div className="text-sm opacity-80">{it.price ? `${it.price} ${it.currency || ""}` : "—"}</div>

                <div className="mt-2 flex gap-3">
                  {it.item_web_url && (
                    <a className="text-blue-700 underline" href={it.item_web_url} target="_blank" rel="noreferrer">
                      View
                    </a>
                  )}
                  {it.affiliate_url && (
                    <a className="text-green-700 underline" href={it.affiliate_url} target="_blank" rel="noreferrer">
                      Affiliate
                    </a>
                  )}
                </div>
              </article>
            ))}
          </div>

          {!loading && items.length === 0 && (
            <div className="mt-3 text-sm text-slate-600">No results yet. Try another query.</div>
          )}
        </>
      ) : (
        <div className="mt-3 text-sm text-slate-600">
          This tab will open eBay in a new tab using your affiliate link.
        </div>
      )}
    </Section>
  );
}
