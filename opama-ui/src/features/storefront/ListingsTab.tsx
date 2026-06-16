import React, { useState } from "react";
import { Pencil, Check, X, ExternalLink } from "lucide-react";
import { api, API_BASE } from "../../lib/api";
import type { StorefrontListing } from "./types";

interface Props {
  listings: StorefrontListing[];
  onUpdated: (item: StorefrontListing) => void;
  onToast: (msg: string, type?: "success" | "error" | "info") => void;
}

function fmtCAD(n: number | null) {
  if (n == null) return "—";
  return `$${n.toFixed(2)} CAD`;
}

interface RowProps {
  item: StorefrontListing;
  onSaved: (updated: StorefrontListing) => void;
  onToast: Props["onToast"];
}

function ListingRow({ item, onSaved, onToast }: RowProps) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    listing_price_cad: item.listing_price_cad ?? "",
    shipping_price_cad: item.shipping_price_cad ?? "",
    website_slug: item.website_slug ?? "",
    marketplace_ebay: item.marketplace_ebay ?? "",
    marketplace_facebook: item.marketplace_facebook ?? "",
    marketplace_kijiji: item.marketplace_kijiji ?? "",
    marketplace_craigslist: item.marketplace_craigslist ?? "",
  });

  const thumb = item.image_thumb_url || item.image_url;
  const imgSrc = thumb ? (thumb.startsWith("/") ? `${API_BASE}${thumb}` : thumb) : null;

  const save = async () => {
    setSaving(true);
    try {
      const payload: Record<string, unknown> = {};
      if (form.listing_price_cad !== "") payload.listing_price_cad = parseFloat(String(form.listing_price_cad));
      if (form.shipping_price_cad !== "") payload.shipping_price_cad = parseFloat(String(form.shipping_price_cad));
      payload.website_slug = form.website_slug || null;
      payload.marketplace_ebay = form.marketplace_ebay || null;
      payload.marketplace_facebook = form.marketplace_facebook || null;
      payload.marketplace_kijiji = form.marketplace_kijiji || null;
      payload.marketplace_craigslist = form.marketplace_craigslist || null;

      const updated = await api<StorefrontListing>(`/storefront/listings/${item.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      onSaved({ ...item, ...updated });
      setEditing(false);
      onToast("Listing updated", "success");
    } catch {
      onToast("Failed to update listing", "error");
    } finally {
      setSaving(false);
    }
  };

  const isSold = !!item.sale_date;

  return (
    <div className={`bg-white border rounded-xl p-4 space-y-3 ${isSold ? "opacity-60" : ""}`}>
      {/* Header row */}
      <div className="flex items-start gap-3">
        {imgSrc ? (
          <img src={imgSrc} alt={item.name} className="w-14 h-20 object-cover rounded-lg bg-slate-100 flex-shrink-0" />
        ) : (
          <div className="w-14 h-20 rounded-lg bg-slate-100 flex-shrink-0" />
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <div>
              <div className="font-semibold text-slate-800 text-sm leading-tight">{item.name}</div>
              <div className="flex gap-1.5 mt-1 flex-wrap">
                <span className="text-xs bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded-full">{item.category}</span>
                {item.condition && <span className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">{item.condition}</span>}
                {isSold && <span className="text-xs bg-red-100 text-red-600 px-2 py-0.5 rounded-full font-medium">SOLD</span>}
              </div>
            </div>
            {!isSold && !editing && (
              <button onClick={() => setEditing(true)} className="text-slate-400 hover:text-indigo-600 flex-shrink-0">
                <Pencil className="w-4 h-4" />
              </button>
            )}
          </div>

          {!editing ? (
            <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-slate-600">
              <div><span className="text-slate-400">Price: </span>{fmtCAD(item.listing_price_cad)}</div>
              <div><span className="text-slate-400">Shipping: </span>{fmtCAD(item.shipping_price_cad)}</div>
              <div className="col-span-2"><span className="text-slate-400">Slug: </span>
                <span className="font-mono">{item.website_slug || <em className="text-slate-300">not set</em>}</span>
              </div>
              {(item.marketplace_ebay || item.marketplace_facebook || item.marketplace_kijiji || item.marketplace_craigslist) && (
                <div className="col-span-2 flex gap-2 flex-wrap mt-1">
                  {item.marketplace_ebay && <a href={item.marketplace_ebay} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 text-indigo-600 hover:underline"><ExternalLink className="w-3 h-3" />eBay</a>}
                  {item.marketplace_facebook && <a href={item.marketplace_facebook} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 text-indigo-600 hover:underline"><ExternalLink className="w-3 h-3" />Facebook</a>}
                  {item.marketplace_kijiji && <a href={item.marketplace_kijiji} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 text-indigo-600 hover:underline"><ExternalLink className="w-3 h-3" />Kijiji</a>}
                  {item.marketplace_craigslist && <a href={item.marketplace_craigslist} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 text-indigo-600 hover:underline"><ExternalLink className="w-3 h-3" />Craigslist</a>}
                </div>
              )}
            </div>
          ) : (
            <div className="mt-3 space-y-2">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-xs text-slate-500 mb-0.5 block">Price CAD</label>
                  <input type="number" min={0} step="0.01" value={form.listing_price_cad}
                    onChange={e => setForm(f => ({ ...f, listing_price_cad: e.target.value }))}
                    className="w-full border border-slate-200 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
                </div>
                <div>
                  <label className="text-xs text-slate-500 mb-0.5 block">Shipping CAD</label>
                  <input type="number" min={0} step="0.01" value={form.shipping_price_cad}
                    onChange={e => setForm(f => ({ ...f, shipping_price_cad: e.target.value }))}
                    className="w-full border border-slate-200 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
                </div>
              </div>
              <div>
                <label className="text-xs text-slate-500 mb-0.5 block">URL Slug</label>
                <input value={form.website_slug} onChange={e => setForm(f => ({ ...f, website_slug: e.target.value }))}
                  placeholder="my-item-slug" className="w-full border border-slate-200 rounded px-2 py-1 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-indigo-400" />
              </div>
              {(["ebay", "facebook", "kijiji", "craigslist"] as const).map(k => (
                <div key={k}>
                  <label className="text-xs text-slate-500 mb-0.5 block capitalize">{k} URL</label>
                  <input value={(form as any)[`marketplace_${k}`]}
                    onChange={e => setForm(f => ({ ...f, [`marketplace_${k}`]: e.target.value }))}
                    placeholder={`https://www.${k}.ca/…`}
                    className="w-full border border-slate-200 rounded px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-400" />
                </div>
              ))}
              <div className="flex gap-2 pt-1">
                <button onClick={save} disabled={saving}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 text-white rounded-lg text-xs font-medium hover:bg-indigo-700 disabled:opacity-50">
                  <Check className="w-3.5 h-3.5" />{saving ? "Saving…" : "Save"}
                </button>
                <button onClick={() => setEditing(false)} className="flex items-center gap-1.5 px-3 py-1.5 border border-slate-200 rounded-lg text-xs text-slate-600 hover:bg-slate-50">
                  <X className="w-3.5 h-3.5" />Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ListingsTab({ listings, onUpdated, onToast }: Props) {
  const available = listings.filter(l => !l.sale_date);
  const sold = listings.filter(l => !!l.sale_date);

  if (listings.length === 0) {
    return (
      <div className="py-20 text-center text-slate-400 space-y-2">
        <div className="text-4xl">🏷️</div>
        <div className="font-medium text-slate-600">No active listings</div>
        <p className="text-sm">Toggle "List on storefront website" on any collection item to add it here.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {available.length > 0 && (
        <section className="space-y-3">
          <h3 className="text-sm font-semibold text-slate-600 uppercase tracking-wide">
            Available · {available.length}
          </h3>
          {available.map(item => (
            <ListingRow key={item.id} item={item} onSaved={onUpdated} onToast={onToast} />
          ))}
        </section>
      )}
      {sold.length > 0 && (
        <section className="space-y-3">
          <h3 className="text-sm font-semibold text-slate-600 uppercase tracking-wide">
            Sold · {sold.length}
          </h3>
          {sold.map(item => (
            <ListingRow key={item.id} item={item} onSaved={onUpdated} onToast={onToast} />
          ))}
        </section>
      )}
    </div>
  );
}
