import React, { useState } from "react";
import { Plus, Trash2, Upload, X } from "lucide-react";
import { API_BASE } from "../../lib/api";
import { getAuthToken } from "../../lib/authToken";
import { orgHeader } from "../../lib/activeOrg";
import type { AssetFormData, CustomField } from "./types";

const CONDITIONS = ["Mint", "Near Mint", "Excellent", "Good", "Fair", "Poor", "Damaged"];

const DEFAULT_CATEGORIES = [
  // Vehicles
  "Car", "Motorcycle", "Truck", "Boat", "RV", "Bicycle", "Scooter", "Aircraft",
  // Collectibles
  "Trading Card", "Sports Card", "Comic Book", "Manga", "Action Figure", "Funko Pop",
  "LEGO Set", "Board Game", "Video Game", "Console", "Retro Computer",
  // Jewelry & Accessories
  "Watch", "Jewelry", "Ring", "Necklace", "Bracelet", "Earrings", "Handbag", "Sunglasses",
  // Instruments & Audio
  "Guitar", "Bass Guitar", "Amplifier", "Piano", "Drum Kit", "Vinyl Record", "Turntable",
  // Art & Antiques
  "Painting", "Print", "Sculpture", "Photograph", "Poster", "Antique", "Furniture",
  // Numismatic & Philatelic
  "Coin", "Banknote", "Stamp", "Medal",
  // Spirits & Consumables
  "Wine", "Whisky", "Bourbon", "Rum", "Beer", "Champagne",
  // Fashion
  "Sneakers", "Streetwear", "Vintage Clothing", "Designer Clothing",
  // Memorabilia
  "Signed Memorabilia", "Sports Jersey", "Movie Prop", "Autograph",
  // Real Assets
  "Real Estate", "Land", "Precious Metal", "Gold", "Silver",
  // Other
  "Book", "Camera", "Lens", "Electronics", "Tool", "Other",
];

interface Props {
  userId: number;
  assetId?: number;
  initial?: Partial<AssetFormData>;
  existingCategories?: string[];
  templateConditions?: string[];
  onSubmit: (data: AssetFormData) => Promise<void>;
  onCancel: () => void;
  submitLabel?: string;
}

const EMPTY: AssetFormData = {
  user_id: 0,
  name: "",
  category: "",
  condition: null,
  quantity: 1,
  purchase_price: null,
  purchase_date: null,
  estimated_value: null,
  description: null,
  image_url: null,
  back_image_url: null,
  tags: null,
  custom_fields: [],
  listed_on_website: false,
  listing_price_cad: null,
  shipping_price_cad: null,
  website_slug: null,
  sale_price_cad: null,
  sale_date: null,
  sale_platform: null,
};

export default function AssetForm({ userId, assetId, initial, existingCategories = [], templateConditions, onSubmit, onCancel, submitLabel = "Save" }: Props) {
  const categoryOptions = Array.from(new Set([...existingCategories, ...DEFAULT_CATEGORIES])).sort();
  const conditionOptions = templateConditions ?? CONDITIONS;
  const [form, setForm] = useState<AssetFormData>({ ...EMPTY, ...initial, user_id: userId });
  const [fields, setFields] = useState<CustomField[]>(initial?.custom_fields ?? []);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadingBack, setUploadingBack] = useState(false);

  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !assetId) return;
    setUploading(true);
    try {
      const token = await getAuthToken();
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`${API_BASE}/assets/${assetId}/image`, {
        method: "POST",
        headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...orgHeader() },
        body: fd,
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const { image_url } = await res.json();
      set("image_url", image_url);
    } catch (err: any) {
      alert(`Upload failed: ${err.message}`);
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  const handleBackImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !assetId) return;
    setUploadingBack(true);
    try {
      const token = await getAuthToken();
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`${API_BASE}/assets/${assetId}/back-image`, {
        method: "POST",
        headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...orgHeader() },
        body: fd,
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const { back_image_url } = await res.json();
      set("back_image_url", back_image_url);
    } catch (err: any) {
      alert(`Upload failed: ${err.message}`);
    } finally {
      setUploadingBack(false);
      e.target.value = "";
    }
  };

  const set = (key: keyof AssetFormData, val: unknown) =>
    setForm((f) => ({ ...f, [key]: val }));

  const slugify = (s: string) =>
    s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80);

  const handleNameChange = (val: string) => {
    set("name", val);
    // Auto-fill slug only if it hasn't been manually edited
    if (!form.website_slug || form.website_slug === slugify(form.name)) {
      set("website_slug", slugify(val));
    }
  };

  const addField = () => setFields((f) => [...f, { key: "", value: "" }]);
  const removeField = (i: number) => setFields((f) => f.filter((_, j) => j !== i));
  const updateField = (i: number, k: "key" | "value", v: string) =>
    setFields((f) => f.map((field, j) => (j === i ? { ...field, [k]: v } : field)));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await onSubmit({ ...form, custom_fields: fields.filter((f) => f.key.trim()) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      {/* Core fields */}
      <div className="grid sm:grid-cols-2 gap-4">
        <div className="sm:col-span-2">
          <label className="block text-sm font-medium text-slate-700 mb-1">Name *</label>
          <input
            required
            value={form.name}
            onChange={(e) => handleNameChange(e.target.value)}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
            placeholder="e.g. 1959 Gibson Les Paul Standard"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Category *</label>
          <input
            required
            value={form.category}
            onChange={(e) => set("category", e.target.value)}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
            placeholder="e.g. Guitar, Watch, Wine"
            list="category-suggestions"
          />
          <datalist id="category-suggestions">
            {categoryOptions.map((c) => <option key={c} value={c} />)}
          </datalist>
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Condition</label>
          <select
            value={form.condition ?? ""}
            onChange={(e) => set("condition", e.target.value || null)}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
          >
            <option value="">— select —</option>
            {conditionOptions.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Quantity</label>
          <input
            type="number"
            min={1}
            value={form.quantity}
            onChange={(e) => set("quantity", parseInt(e.target.value) || 1)}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Purchase Date</label>
          <input
            type="date"
            value={form.purchase_date ?? ""}
            onChange={(e) => set("purchase_date", e.target.value || null)}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Purchase Price ($)</label>
          <input
            type="number"
            min={0}
            step="0.01"
            value={form.purchase_price ?? ""}
            onChange={(e) => set("purchase_price", e.target.value ? parseFloat(e.target.value) : null)}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
            placeholder="0.00"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Estimated Value ($)</label>
          <input
            type="number"
            min={0}
            step="0.01"
            value={form.estimated_value ?? ""}
            onChange={(e) => set("estimated_value", e.target.value ? parseFloat(e.target.value) : null)}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
            placeholder="0.00"
          />
        </div>

        <div className="sm:col-span-2">
          <label className="block text-sm font-medium text-slate-700 mb-1">Description</label>
          <textarea
            rows={3}
            value={form.description ?? ""}
            onChange={(e) => set("description", e.target.value || null)}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 resize-none"
            placeholder="Notes, provenance, serial numbers…"
          />
        </div>

        <div className="sm:col-span-2">
          <label className="block text-sm font-medium text-slate-700 mb-1">Image</label>
          <div className={`flex gap-3 ${form.image_url ? "items-start" : "items-center"}`}>
            {form.image_url && (
              <div className="relative flex-shrink-0">
                <img
                  src={form.image_url.startsWith("/") ? `${API_BASE}${form.image_url}` : form.image_url}
                  alt=""
                  className="w-20 h-20 object-cover rounded-lg border border-slate-200 bg-slate-50"
                  onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                />
                <button
                  type="button"
                  onClick={() => set("image_url", null)}
                  title="Remove image"
                  className="absolute -top-1.5 -right-1.5 bg-white rounded-full border border-slate-200 p-0.5 text-slate-400 hover:text-red-500 shadow-sm"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            )}
            <div className="flex-1 space-y-2">
              <input
                value={form.image_url?.startsWith("/") ? "" : (form.image_url ?? "")}
                onChange={(e) => set("image_url", e.target.value || null)}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
                placeholder={assetId ? "Paste a URL, or upload below…" : "https://…"}
              />
              {assetId ? (
                <label className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-dashed border-slate-300 text-xs text-slate-500 cursor-pointer hover:border-indigo-400 hover:text-indigo-600 transition ${uploading ? "opacity-50 pointer-events-none" : ""}`}>
                  <Upload className="w-3.5 h-3.5" />
                  {uploading ? "Uploading…" : "Upload image"}
                  <input type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={handleImageUpload} disabled={uploading} />
                </label>
              ) : (
                <p className="text-xs text-slate-400">Save this item first to enable file upload.</p>
              )}
            </div>
          </div>
        </div>

        <div className="sm:col-span-2">
          <label className="block text-sm font-medium text-slate-700 mb-1">Back Image</label>
          <div className={`flex gap-3 ${form.back_image_url ? "items-start" : "items-center"}`}>
            {form.back_image_url && (
              <div className="relative flex-shrink-0">
                <img
                  src={form.back_image_url.startsWith("/") ? `${API_BASE}${form.back_image_url}` : form.back_image_url}
                  alt=""
                  className="w-20 h-20 object-cover rounded-lg border border-slate-200 bg-slate-50"
                  onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                />
                <button
                  type="button"
                  onClick={() => set("back_image_url", null)}
                  title="Remove back image"
                  className="absolute -top-1.5 -right-1.5 bg-white rounded-full border border-slate-200 p-0.5 text-slate-400 hover:text-red-500 shadow-sm"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            )}
            <div className="flex-1 space-y-2">
              <input
                value={form.back_image_url?.startsWith("/") ? "" : (form.back_image_url ?? "")}
                onChange={(e) => set("back_image_url", e.target.value || null)}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
                placeholder={assetId ? "Paste a URL, or upload below…" : "https://…"}
              />
              {assetId ? (
                <label className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-dashed border-slate-300 text-xs text-slate-500 cursor-pointer hover:border-indigo-400 hover:text-indigo-600 transition ${uploadingBack ? "opacity-50 pointer-events-none" : ""}`}>
                  <Upload className="w-3.5 h-3.5" />
                  {uploadingBack ? "Uploading…" : "Upload back image"}
                  <input type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={handleBackImageUpload} disabled={uploadingBack} />
                </label>
              ) : (
                <p className="text-xs text-slate-400">Save this item first to enable file upload.</p>
              )}
            </div>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Tags</label>
          <input
            value={form.tags ?? ""}
            onChange={(e) => set("tags", e.target.value || null)}
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
            placeholder="vintage, signed, ltd-edition"
          />
        </div>
      </div>

      {/* Website listing */}
      <div className="border border-slate-200 rounded-xl p-4 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold text-slate-700">List on storefront website</p>
            <p className="text-xs text-slate-400 mt-0.5">Publish this item to the collectibles shop</p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={form.listed_on_website}
            onClick={() => set("listed_on_website", !form.listed_on_website)}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:ring-offset-1 ${
              form.listed_on_website ? "bg-indigo-600" : "bg-slate-200"
            }`}
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                form.listed_on_website ? "translate-x-6" : "translate-x-1"
              }`}
            />
          </button>
        </div>

        {form.listed_on_website && (
          <div className="grid sm:grid-cols-2 gap-4 pt-1">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Listing Price CAD *</label>
              <input
                type="number"
                min={0}
                step="0.01"
                required={form.listed_on_website}
                value={form.listing_price_cad ?? ""}
                onChange={(e) => set("listing_price_cad", e.target.value ? parseFloat(e.target.value) : null)}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
                placeholder="0.00"
              />
            </div>

            <div className="sm:col-span-2">
              <label className="block text-sm font-medium text-slate-700 mb-1">URL Slug</label>
              <input
                value={form.website_slug ?? ""}
                onChange={(e) => set("website_slug", e.target.value || null)}
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-400"
                placeholder="auto-generated from name"
              />
              <p className="text-xs text-slate-400 mt-1">Used as the item ID in the catalog — lowercase, hyphens only.</p>
            </div>
          </div>
        )}

        {form.sale_date && (
          <div className="bg-green-50 border border-green-200 rounded-lg px-3 py-2 text-sm text-green-800">
            ✓ Sold on {form.sale_date} via {form.sale_platform ?? "unknown"} for ${form.sale_price_cad?.toFixed(2)} CAD
          </div>
        )}
      </div>

      {/* Custom fields */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-slate-700">Custom Fields</span>
          <button
            type="button"
            onClick={addField}
            className="flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-800"
          >
            <Plus className="w-3 h-3" /> Add Field
          </button>
        </div>
        {fields.length === 0 && (
          <p className="text-xs text-slate-400">
            Add domain-specific fields — serial number, year, make, model, vintage, etc.
          </p>
        )}
        <div className="space-y-2">
          {fields.map((f, i) => (
            <div key={i} className="flex gap-2 items-center">
              <input
                value={f.key}
                onChange={(e) => updateField(i, "key", e.target.value)}
                placeholder="Field name"
                className="flex-1 border border-slate-200 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
              />
              <input
                value={f.value}
                onChange={(e) => updateField(i, "value", e.target.value)}
                placeholder="Value"
                className="flex-1 border border-slate-200 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
              />
              <button type="button" onClick={() => removeField(i)} className="text-slate-400 hover:text-red-500">
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-2 justify-end pt-2">
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 rounded-lg border border-slate-200 text-sm hover:bg-slate-50"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={saving}
          className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium disabled:opacity-50"
        >
          {saving ? "Saving…" : submitLabel}
        </button>
      </div>
    </form>
  );
}
