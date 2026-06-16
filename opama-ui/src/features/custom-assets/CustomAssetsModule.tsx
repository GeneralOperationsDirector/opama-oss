/**
 * CustomAssetsModule — the Collections module (any asset class).
 *
 * The main whitelabel surface: grid of the user's items, filtering by
 * category/search, create/edit via AssetForm, and detail/lightbox viewing.
 * Receives a navigation arg from the dashboard that selects the initial
 * category — either a template id (resolved to its category) or a literal
 * "category:Name" string (see the navigation notes in CLAUDE.md). Talks to
 * the backend /assets endpoints.
 */
import React, { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Plus, Search, TrendingUp, TrendingDown, Package, DollarSign, BarChart3 } from "lucide-react";
import { api, API_BASE } from "../../lib/api";
import ConfirmModal from "../../shared/atoms/ConfirmModal";
import type { CustomAsset, AssetFormData, PortfolioSummary } from "./types";
import AssetCard from "./AssetCard";
import AssetForm from "./AssetForm";
import ImageLightbox from "./ImageLightbox";
import TemplatePicker from "../collections/TemplatePicker";
import { TEMPLATE_MAP, type CollectionTemplate } from "../collections/templates";

interface Props {
  userId: number;
  onToast: (msg: string, type?: "success" | "error" | "info") => void;
  pendingTemplateId?: string | null;
  onPendingTemplateConsumed?: () => void;
}

function fmt(n: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(n);
}

type View = "list" | "template" | "create" | "edit" | "detail";

export default function CustomAssetsModule({ userId, onToast, pendingTemplateId, onPendingTemplateConsumed }: Props) {
  const [assets, setAssets] = useState<CustomAsset[]>([]);
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [categories, setCategories] = useState<string[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<View>("list");
  const [editing, setEditing] = useState<CustomAsset | null>(null);
  const [detail, setDetail] = useState<CustomAsset | null>(null);
  const [pendingDelete, setPendingDelete] = useState<CustomAsset | null>(null);
  const [selectedTemplate, setSelectedTemplate] = useState<CollectionTemplate | null>(null);
  const [lightboxImages, setLightboxImages] = useState<{ src: string; label?: string }[]>([]);
  const [lightboxIndex, setLightboxIndex] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ user_id: String(userId) });
      if (selectedCategory !== "all") params.set("category", selectedCategory);
      if (query) params.set("q", query);

      const [assetData, summaryData, catData] = await Promise.all([
        api<CustomAsset[]>(`/assets?${params}`),
        api<PortfolioSummary>(`/assets/summary?user_id=${userId}`),
        api<string[]>(`/assets/categories?user_id=${userId}`),
      ]);
      setAssets(assetData);
      setSummary(summaryData);
      setCategories(catData);
    } catch (e) {
      onToast("Failed to load collections", "error");
    } finally {
      setLoading(false);
    }
  }, [userId, selectedCategory, query, onToast]);

  useEffect(() => { load(); }, [load]);

  // Apply a template or direct category filter selected on the dashboard.
  // "category:Art" navigates straight to that category without a template.
  useEffect(() => {
    if (!pendingTemplateId) return;
    if (pendingTemplateId.startsWith("category:")) {
      const cat = pendingTemplateId.slice("category:".length);
      setSelectedCategory(cat);
      setView("list");
    } else {
      const template = TEMPLATE_MAP[pendingTemplateId];
      if (template) {
        setSelectedTemplate(template);
        setSelectedCategory(template.category);
        setView("list");
      }
    }
    onPendingTemplateConsumed?.();
  }, [pendingTemplateId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Listen for portfolio drill-in (filter by category)
  useEffect(() => {
    const handler = (e: Event) => {
      const category = (e as CustomEvent).detail as string;
      if (category) {
        setSelectedCategory(category);
        setView("list");
      }
    };
    window.addEventListener("filterCollectionCategory", handler);
    return () => window.removeEventListener("filterCollectionCategory", handler);
  }, []);

  const handleTemplateSelect = (template: CollectionTemplate) => {
    setSelectedTemplate(template);
    setView("create");
  };

  const handleCreate = async (data: AssetFormData) => {
    await api("/assets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    onToast("Item added", "success");
    setSelectedTemplate(null);
    setView("list");
    load();
  };

  const handleUpdate = async (data: AssetFormData) => {
    if (!editing) return;
    await api(`/assets/${editing.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    onToast("Item updated", "success");
    setEditing(null);
    setView("list");
    load();
  };

  const confirmDelete = async () => {
    if (!pendingDelete) return;
    await api(`/assets/${pendingDelete.id}`, { method: "DELETE" });
    setPendingDelete(null);
    onToast("Item deleted", "info");
    load();
  };

  const backToList = () => {
    setView("list");
    setEditing(null);
    setSelectedTemplate(null);
  };

  // ── Summary bar ─────────────────────────────────────────────────────────
  const SummaryBar = summary ? (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {[
        { icon: <Package className="w-4 h-4" />, label: "Total Items", value: summary.total_assets.toString(), color: "text-indigo-600" },
        { icon: <DollarSign className="w-4 h-4" />, label: "Total Cost", value: fmt(summary.total_cost), color: "text-slate-700" },
        { icon: <BarChart3 className="w-4 h-4" />, label: "Est. Value", value: fmt(summary.total_estimated_value), color: "text-slate-700" },
        {
          icon: summary.unrealized_gain >= 0
            ? <TrendingUp className="w-4 h-4" />
            : <TrendingDown className="w-4 h-4" />,
          label: "Unrealized Gain",
          value: fmt(summary.unrealized_gain),
          color: summary.unrealized_gain >= 0 ? "text-emerald-600" : "text-red-500",
        },
      ].map((s) => (
        <div key={s.label} className="bg-white rounded-xl border border-slate-200 p-3 flex items-center gap-3">
          <div className={s.color}>{s.icon}</div>
          <div>
            <div className="text-xs text-slate-400">{s.label}</div>
            <div className={`font-semibold text-sm ${s.color}`}>{s.value}</div>
          </div>
        </div>
      ))}
    </div>
  ) : null;

  // ── Detail view ─────────────────────────────────────────────────────────
  if (view === "detail" && detail) {
    return (
      <div className="space-y-4">
        <button onClick={backToList} className="text-sm text-indigo-600 hover:underline flex items-center gap-1">
          ← Back to Collections
        </button>
        <div className="bg-white rounded-2xl border border-slate-200 p-6 space-y-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-xl font-bold text-slate-800">{detail.name}</h2>
              <div className="flex gap-2 mt-1">
                <span className="text-xs bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded-full">{detail.category}</span>
                {detail.condition && <span className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">{detail.condition}</span>}
              </div>
            </div>
            <button
              onClick={() => { setEditing(detail); setView("edit"); }}
              className="px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-sm hover:bg-indigo-700"
            >
              Edit
            </button>
          </div>

          {(detail.image_url || detail.back_image_url) && (() => {
            const resolve = (url: string) => url.startsWith("/") ? `${API_BASE}${url}` : url;
            const images = [
              detail.image_url ? { src: resolve(detail.image_url), label: "Front" } : null,
              detail.back_image_url ? { src: resolve(detail.back_image_url), label: "Back" } : null,
            ].filter(Boolean) as { src: string; label: string }[];
            const hasBoth = images.length === 2;

            return (
              <div className={`flex gap-3 ${hasBoth ? "justify-center" : ""}`}>
                {images.map((img, i) => (
                  <button
                    key={img.label}
                    onClick={() => { setLightboxImages(images); setLightboxIndex(i); }}
                    className={`group relative overflow-hidden rounded-xl bg-slate-50 cursor-zoom-in ${hasBoth ? "flex-1 max-w-[48%]" : "w-full"}`}
                  >
                    <img
                      src={img.src}
                      alt={img.label}
                      className="w-full object-contain max-h-72"
                    />
                    {hasBoth && (
                      <div className="absolute bottom-0 inset-x-0 py-1 bg-black/30 text-white text-xs text-center font-medium opacity-0 group-hover:opacity-100 transition-opacity">
                        {img.label}
                      </div>
                    )}
                  </button>
                ))}
              </div>
            );
          })()}

          <div className="grid sm:grid-cols-2 gap-4 text-sm">
            {[
              ["Quantity", detail.quantity],
              ["Purchase Price", detail.purchase_price != null ? fmt(detail.purchase_price) : "—"],
              ["Estimated Value", detail.estimated_value != null ? fmt(detail.estimated_value) : "—"],
              ["Purchase Date", detail.purchase_date ?? "—"],
              ["Tags", detail.tags ?? "—"],
            ].map(([label, val]) => (
              <div key={String(label)}>
                <div className="text-slate-400 text-xs">{label}</div>
                <div className="font-medium text-slate-700">{String(val)}</div>
              </div>
            ))}
          </div>

          {detail.description && (
            <div>
              <div className="text-slate-400 text-xs mb-1">Notes</div>
              <p className="text-sm text-slate-700 whitespace-pre-wrap">{detail.description}</p>
            </div>
          )}

          {detail.custom_fields.length > 0 && (
            <div>
              <div className="text-slate-400 text-xs mb-2">Details</div>
              <div className="grid sm:grid-cols-2 gap-2">
                {detail.custom_fields.map((f) => (
                  <div key={f.id ?? f.key} className="bg-slate-50 rounded-lg px-3 py-2">
                    <div className="text-xs text-slate-400">{f.key}</div>
                    <div className="text-sm font-medium text-slate-700">{f.value || "—"}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {lightboxImages.length > 0 && (
          <ImageLightbox
            images={lightboxImages}
            index={lightboxIndex}
            onNavigate={setLightboxIndex}
            onClose={() => setLightboxImages([])}
          />
        )}
      </div>
    );
  }

  // ── Create / Edit form ──────────────────────────────────────────────────
  if (view === "create" || view === "edit") {
    // Build initial data from template (create) or existing asset (edit)
    const initialData: Partial<AssetFormData> = editing
      ? { ...editing }
      : selectedTemplate
      ? {
          category: selectedTemplate.category,
          custom_fields: selectedTemplate.fields.map((key) => ({ key, value: "" })),
        }
      : {};

    return (
      <div className="space-y-4">
        <button onClick={backToList} className="text-sm text-indigo-600 hover:underline flex items-center gap-1">
          ← Back to Collections
        </button>
        <div className="bg-white rounded-2xl border border-slate-200 p-6">
          <div className="flex items-center gap-3 mb-5">
            {selectedTemplate && !editing && (
              <span className="text-3xl">{selectedTemplate.emoji}</span>
            )}
            <h2 className="text-lg font-bold text-slate-800">
              {editing ? `Edit: ${editing.name}` : selectedTemplate ? `New ${selectedTemplate.name}` : "New Item"}
            </h2>
          </div>
          <AssetForm
            userId={userId}
            assetId={editing?.id}
            initial={initialData}
            existingCategories={categories}
            templateConditions={selectedTemplate?.conditions}
            onSubmit={editing ? handleUpdate : handleCreate}
            onCancel={backToList}
            submitLabel={editing ? "Save Changes" : "Add Item"}
          />
        </div>
      </div>
    );
  }

  // ── List view ───────────────────────────────────────────────────────────
  return (
    <div className="space-y-5">
      {/* Template picker overlay */}
      {view === "template" && (
        <TemplatePicker
          recentCategories={categories}
          onSelect={handleTemplateSelect}
          onClose={() => setView("list")}
        />
      )}

      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          {selectedTemplate && selectedCategory !== "all" && (
            <span className="text-2xl leading-none">{selectedTemplate.emoji}</span>
          )}
          <div>
            <h2 className="text-xl font-bold text-slate-800">
              {selectedCategory && selectedCategory !== "all" ? selectedCategory : "Collections"}
            </h2>
            {selectedCategory && selectedCategory !== "all" && (
              <button
                onClick={() => { setSelectedCategory("all"); setSelectedTemplate(null); }}
                className="text-xs text-slate-400 hover:text-indigo-600"
              >
                ← All Collections
              </button>
            )}
          </div>
        </div>
        <button
          onClick={() => selectedTemplate ? setView("create") : setView("template")}
          className="flex items-center gap-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-medium"
        >
          <Plus className="w-4 h-4" />
          {selectedTemplate && selectedCategory !== "all" ? `Add ${selectedTemplate.name}` : "Add Item"}
        </button>
      </div>

      {/* Summary */}
      {SummaryBar}

      {/* Filters */}
      <div className="flex flex-wrap gap-2 items-center">
        <div className="relative flex-1 min-w-48">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search items…"
            className="w-full pl-9 pr-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
          />
        </div>
        <div className="flex gap-1.5 flex-wrap">
          {["all", ...categories].map((cat) => (
            <button
              key={cat}
              onClick={() => setSelectedCategory(cat)}
              className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                selectedCategory === cat
                  ? "bg-indigo-600 text-white"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {cat === "all" ? "All" : cat}
            </button>
          ))}
        </div>
      </div>

      {/* Grid */}
      {loading ? (
        <div className="text-sm text-slate-400 py-12 text-center">Loading…</div>
      ) : assets.length === 0 ? (
        <div className="py-20 text-center space-y-3">
          <div className="text-4xl">{selectedTemplate?.emoji ?? "📦"}</div>
          <div className="text-slate-500 font-medium">
            {selectedTemplate && selectedCategory !== "all"
              ? `No ${selectedTemplate.name}s tracked yet`
              : "No items yet"}
          </div>
          <div className="text-sm text-slate-400">
            {selectedTemplate && selectedCategory !== "all"
              ? `Add your first ${selectedTemplate.name.toLowerCase()} to start tracking your collection.`
              : "Start tracking anything — guitars, watches, wine, art, or whatever you collect."}
          </div>
          <button
            onClick={() => selectedTemplate ? setView("create") : setView("template")}
            className="mt-2 inline-flex items-center gap-1.5 px-4 py-2 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700"
          >
            <Plus className="w-4 h-4" />
            {selectedTemplate && selectedCategory !== "all"
              ? `Add your first ${selectedTemplate.name}`
              : "Add your first item"}
          </button>
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          <AnimatePresence>
            {assets.map((asset, i) => (
              <motion.div
                key={asset.id}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95 }}
                transition={{ delay: i * 0.03 }}
              >
                <AssetCard
                  asset={asset}
                  userId={userId}
                  onEdit={() => { setEditing(asset); setView("edit"); }}
                  onDelete={() => setPendingDelete(asset)}
                  onOpen={() => { setDetail(asset); setView("detail"); }}
                  onToast={onToast}
                />
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}

      {pendingDelete && (
        <ConfirmModal
          title="Delete item?"
          message={`"${pendingDelete.name}" will be permanently deleted.`}
          confirmLabel="Delete"
          destructive
          onConfirm={confirmDelete}
          onCancel={() => setPendingDelete(null)}
        />
      )}

      {lightboxImages.length > 0 && (
        <ImageLightbox
          images={lightboxImages}
          index={lightboxIndex}
          onNavigate={setLightboxIndex}
          onClose={() => setLightboxImages([])}
        />
      )}
    </div>
  );
}
