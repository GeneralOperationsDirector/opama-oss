/**
 * DashboardView — the landing screen.
 *
 * Fetches /assets/summary and renders one card per category the user actually
 * has items in (each becomes its own clickable collection module), alongside
 * portfolio value and quick actions. Clicking a card calls onSelectModule to
 * navigate into Collections filtered to that category. This is why a brand-new
 * empty instance shows little until items exist — see scripts/seed_demo.py.
 */
import React, { useEffect, useState } from "react";
import { motion } from "motion/react";
import { TrendingUp, Plus, ExternalLink, Loader2, Lock } from "lucide-react";
import type { AppModule } from "../../types";
import { api } from "../../lib/api";
import { useLicense } from "../../contexts/LicenseContext";
import TemplatePicker from "../collections/TemplatePicker";
import { TEMPLATES, CATEGORY_TO_TEMPLATE, type CollectionTemplate } from "../collections/templates";
import { isModuleEnabled } from "../../lib/moduleRegistry";

/* ─── Featured collection templates shown on dashboard ─────────── */
const FEATURED_TEMPLATE_IDS = [
  "stock", "crypto", "bond",
  "watch", "guitar", "sneakers",
  "sports-card", "comic", "wine",
  "coin", "art", "vinyl",
];

const FEATURED_TEMPLATES = FEATURED_TEMPLATE_IDS
  .map((id) => TEMPLATES.find((t) => t.id === id))
  .filter((t): t is CollectionTemplate => !!t);

/* ─── Per-category stat row returned by /assets/summary ─────────── */
interface CategoryStat {
  category: string;
  count: number;
  value: number;
}

/* ─── Per-module live stats ─────────────────────────────────────── */
interface ModuleStats {
  loading: boolean;
  items: number | null;
  value: number | null;
  itemLabel: string;
}
const EMPTY_STATS: ModuleStats = { loading: false, items: null, value: null, itemLabel: "items" };

/* ─── Static module definitions (non-collection) ─────────────────── */
interface ModuleDef {
  id: AppModule;
  name: string;
  description: string;
  itemLabel: string;
  iconEl: React.ReactNode;
}

const STATIC_MODULES: ModuleDef[] = [
  {
    id: "pokemon",
    name: "Pokémon TCG",
    description: "Catalog, inventory, deck building, trading, and portfolio valuation.",
    itemLabel: "cards",
    iconEl: (
      <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-yellow-400 to-orange-500 flex items-center justify-center text-2xl select-none">
        ⚡
      </div>
    ),
  },
  {
    id: "grading",
    name: "Card Grader",
    description: "Upload a scan to estimate PSA-equivalent grade — centering, corners, surface, and edges.",
    itemLabel: "analyses",
    iconEl: (
      <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-emerald-400 to-teal-600 flex items-center justify-center text-2xl select-none">
        🔬
      </div>
    ),
  },
  {
    id: "insurance",
    name: "Insurance & Appraisals",
    description: "Track policy coverage, scheduled items, and appraisal records for your collection.",
    itemLabel: "policies",
    iconEl: (
      <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-sky-400 to-blue-600 flex items-center justify-center text-2xl select-none">
        🛡️
      </div>
    ),
  },
];

/* ─── Fallback "Collections" card shown when user has no items ───── */
const COLLECTIONS_FALLBACK: ModuleDef = {
  id: "custom",
  name: "Collections",
  description: "Track anything — watches, guitars, wine, art, sneakers, coins, and more.",
  itemLabel: "items",
  iconEl: (
    <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-violet-400 to-indigo-500 flex items-center justify-center text-2xl select-none">
      📦
    </div>
  ),
};

/* ─── Helpers ────────────────────────────────────────────────────── */
function fmtValue(n: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD", maximumFractionDigits: 0,
  }).format(n);
}

/* ─── Component ─────────────────────────────────────────────────── */
export default function DashboardView({
  onSelectModule,
  userId,
  onSignUp,
}: {
  onSelectModule: (module: AppModule, tab?: string, templateId?: string) => void;
  userId?: number;
  onSignUp?: () => void;
}) {
  const { isModuleLicensed } = useLicense();
  const [statsMap, setStatsMap] = useState<Record<string, ModuleStats>>({});
  const [activeCategories, setActiveCategories] = useState<CategoryStat[] | null>(null);
  const [showPicker, setShowPicker] = useState(false);

  useEffect(() => {
    if (!userId) return;
    const uid = userId;

    if (isModuleEnabled("pokemon")) {
      setStatsMap({
        pokemon: { ...EMPTY_STATS, loading: true, itemLabel: "cards" },
      });
      Promise.allSettled([
        api<any[]>(`/inventory`),
        api<{ total_value: number }>(`/portfolio/value?user_id=${uid}`),
      ]).then(([invRes, portRes]) => {
        setStatsMap((prev) => ({
          ...prev,
          pokemon: {
            loading: false,
            itemLabel: "cards",
            items: invRes.status === "fulfilled" ? invRes.value.length : null,
            value: portRes.status === "fulfilled" ? portRes.value.total_value ?? null : null,
          },
        }));
      });
    }

    if (isModuleEnabled("insurance")) {
      setStatsMap((prev) => ({
        ...prev,
        insurance: { ...EMPTY_STATS, loading: true, itemLabel: "policies" },
      }));
      api<{ policy_count: number; total_coverage: number }>(`/insurance/summary`)
        .then((s) => {
          setStatsMap((prev) => ({
            ...prev,
            insurance: {
              loading: false,
              itemLabel: "policies",
              items: s.policy_count,
              value: s.total_coverage,
            },
          }));
        })
        .catch(() => {
          setStatsMap((prev) => ({ ...prev, insurance: { ...EMPTY_STATS, itemLabel: "policies" } }));
        });
    }

    api<{ total_assets: number; total_estimated_value: number; categories: CategoryStat[] }>(
      `/assets/summary?user_id=${uid}`
    )
      .then((s) => {
        setActiveCategories(s.categories ?? []);
      })
      .catch(() => {
        setActiveCategories([]);
      });
  }, [userId]);

  const handleTemplateSelect = (template: CollectionTemplate) => {
    setShowPicker(false);
    onSelectModule("custom", undefined, template.id);
  };

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-10">

      {/* Hero */}
      <div className="text-center space-y-2">
        <h2 className="text-4xl font-bold text-slate-800">Your Asset Hub</h2>
        <p className="text-slate-500 text-lg max-w-xl mx-auto">
          Manage, value, and showcase every collection you own — all in one place.
        </p>
        {!userId && onSignUp && (
          <div className="pt-4 flex items-center justify-center gap-3">
            <button
              onClick={onSignUp}
              className="px-6 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold rounded-xl transition-colors shadow-sm text-sm"
            >
              Create a free account
            </button>
            <span className="text-xs text-slate-400">to save your collections</span>
          </div>
        )}
      </div>

      {/* Your Collections */}
      <section>
        <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-4">Your Collections</h3>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">

          {/* Per-category collection cards — one card per active category */}
          {activeCategories === null ? (
            /* Loading state: ghost card */
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="rounded-2xl border border-slate-200 bg-white p-5 flex flex-col gap-3 animate-pulse"
            >
              <div className="w-12 h-12 rounded-xl bg-slate-100" />
              <div className="h-4 bg-slate-100 rounded w-2/3" />
              <div className="h-3 bg-slate-100 rounded w-full" />
            </motion.div>
          ) : activeCategories.length === 0 ? (
            /* No collections yet: show the generic fallback card */
            <motion.button
              key="collections-fallback"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              onClick={() => onSelectModule("custom")}
              className="text-left rounded-2xl border border-slate-200 bg-white hover:shadow-lg hover:-translate-y-0.5 transition-all p-5 flex flex-col gap-3 group"
            >
              <div className="flex items-start justify-between">
                {COLLECTIONS_FALLBACK.iconEl}
                <ExternalLink className="w-3.5 h-3.5 text-slate-300 group-hover:text-indigo-500 transition-colors mt-1" />
              </div>
              <div>
                <div className="font-semibold text-slate-800">{COLLECTIONS_FALLBACK.name}</div>
                <p className="text-sm text-slate-500 mt-0.5">{COLLECTIONS_FALLBACK.description}</p>
              </div>
              <div className="pt-2 border-t border-slate-100 text-xs text-slate-400 italic">No items yet</div>
            </motion.button>
          ) : (
            activeCategories.map((cat, i) => {
              const template = CATEGORY_TO_TEMPLATE[cat.category.toLowerCase()];
              const emoji    = template?.emoji ?? "📦";
              const targetId = template?.id ?? `category:${cat.category}`;
              return (
                <motion.button
                  key={cat.category}
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.08 }}
                  onClick={() => onSelectModule("custom", undefined, targetId)}
                  className="text-left rounded-2xl border border-slate-200 bg-white hover:shadow-lg hover:-translate-y-0.5 transition-all p-5 flex flex-col gap-3 group"
                >
                  <div className="flex items-start justify-between">
                    <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-violet-400 to-indigo-500 flex items-center justify-center text-2xl select-none">
                      {emoji}
                    </div>
                    <ExternalLink className="w-3.5 h-3.5 text-slate-300 group-hover:text-indigo-500 transition-colors mt-1" />
                  </div>
                  <div>
                    <div className="font-semibold text-slate-800">{cat.category}</div>
                    <p className="text-sm text-slate-500 mt-0.5">Collection</p>
                  </div>
                  <div className="pt-2 border-t border-slate-100 flex items-center gap-4 text-xs text-slate-500">
                    <span className="font-medium text-slate-700">
                      {cat.count} {cat.count === 1 ? "item" : "items"}
                    </span>
                    {cat.value > 0 && <span>{fmtValue(cat.value)} est.</span>}
                  </div>
                </motion.button>
              );
            })
          )}

          {/* Add collection — opens template picker */}
          <motion.button
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: (activeCategories?.length ?? 1) * 0.08 }}
            onClick={() => setShowPicker(true)}
            className="rounded-2xl border-2 border-dashed border-slate-200 hover:border-indigo-400 hover:bg-indigo-50 flex flex-col items-center justify-center gap-2 p-5 text-slate-400 hover:text-indigo-600 min-h-[160px] transition-colors group"
          >
            <div className="w-10 h-10 rounded-xl border-2 border-dashed border-slate-300 group-hover:border-indigo-400 flex items-center justify-center transition-colors">
              <Plus className="w-5 h-5" />
            </div>
            <span className="text-sm font-medium">Start a Collection</span>
            <span className="text-xs text-center text-slate-400 group-hover:text-indigo-500">
              Watches, guitars, wine, sneakers&nbsp;…
            </span>
          </motion.button>
        </div>
      </section>

      {/* Your Modules — app features (Pokémon TCG, Card Grader), hidden when none enabled */}
      {STATIC_MODULES.some((mod) => isModuleEnabled(mod.id)) && (
        <section>
          <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-4">Your Modules</h3>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {STATIC_MODULES.filter((mod) => isModuleEnabled(mod.id)).map((mod, i) => {
              const stats = statsMap[mod.id];
              const licensed = isModuleLicensed(mod.id);
              return (
                <motion.button
                  key={mod.id}
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.08 }}
                  onClick={() => licensed && onSelectModule(mod.id)}
                  disabled={!licensed}
                  className={[
                    "relative text-left rounded-2xl border border-slate-200 bg-white p-5 flex flex-col gap-3 group transition-all",
                    licensed
                      ? "hover:shadow-lg hover:-translate-y-0.5 cursor-pointer"
                      : "opacity-70 cursor-default",
                  ].join(" ")}
                >
                  <div className="flex items-start justify-between">
                    {mod.iconEl}
                    {licensed
                      ? <ExternalLink className="w-3.5 h-3.5 text-slate-300 group-hover:text-indigo-500 transition-colors mt-1" />
                      : <Lock className="w-3.5 h-3.5 text-slate-400 mt-1" />
                    }
                  </div>
                  <div>
                    <div className="font-semibold text-slate-800 flex items-center gap-1.5">
                      {mod.name}
                      {!licensed && (
                        <span className="text-[10px] font-semibold uppercase tracking-wide bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-full">
                          Premium
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-slate-500 mt-0.5">{mod.description}</p>
                  </div>
                  {userId && licensed && (
                    <div className="pt-2 border-t border-slate-100 flex items-center gap-4 text-xs text-slate-500">
                      {stats?.loading ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin text-slate-300" />
                      ) : (
                        <>
                          {stats?.items != null && (
                            <span className="font-medium text-slate-700">
                              {stats.items.toLocaleString()} {stats.itemLabel}
                            </span>
                          )}
                          {stats?.value != null && stats.value > 0 && (
                            <span>{fmtValue(stats.value)} est.</span>
                          )}
                          {(!stats || (stats.items === null && stats.value === null)) && (
                            <span className="text-slate-400 italic">No data yet</span>
                          )}
                        </>
                      )}
                    </div>
                  )}
                  {!licensed && (
                    <div className="pt-2 border-t border-slate-100 text-xs text-amber-600 font-medium">
                      Upgrade to unlock
                    </div>
                  )}
                </motion.button>
              );
            })}
          </div>
        </section>
      )}

      {/* Featured collection templates */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">
            Popular Collection Types
          </h3>
          <button
            onClick={() => setShowPicker(true)}
            className="text-xs text-indigo-600 hover:text-indigo-800 font-medium"
          >
            Browse all templates →
          </button>
        </div>
        <div className="grid grid-cols-4 sm:grid-cols-6 lg:grid-cols-6 gap-2">
          {FEATURED_TEMPLATES.map((template, i) => (
            <motion.button
              key={template.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 + i * 0.04 }}
              onClick={() => handleTemplateSelect(template)}
              className="flex flex-col items-center gap-1.5 p-3 rounded-xl border border-slate-200 bg-white hover:border-indigo-400 hover:bg-indigo-50 hover:-translate-y-0.5 transition-all group"
            >
              <span className="text-2xl leading-none">{template.emoji}</span>
              <span className="text-xs font-medium text-slate-600 group-hover:text-indigo-700 text-center leading-tight">
                {template.name}
              </span>
            </motion.button>
          ))}
        </div>
      </section>

      {/* Cross-asset callout */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.5 }}
        className="rounded-2xl bg-gradient-to-r from-indigo-600 to-violet-600 text-white p-6 flex items-center gap-4"
      >
        <TrendingUp className="w-8 h-8 flex-shrink-0 opacity-80" />
        <div>
          <div className="font-semibold text-lg">Portfolio valuation across all collections</div>
          <div className="text-sm opacity-80 mt-0.5">
            As you add collections, your net collection value and P&amp;L will consolidate here automatically.
          </div>
        </div>
      </motion.div>

      {/* Template picker overlay */}
      {showPicker && (
        <TemplatePicker
          onSelect={handleTemplateSelect}
          onClose={() => setShowPicker(false)}
        />
      )}

    </div>
  );
}
