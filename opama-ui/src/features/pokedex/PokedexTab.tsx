import React, { useEffect, useMemo, useState } from "react";
import Section from "../../shared/atoms/Section";
import { useToast } from "../../shared/Toaster";
import PokedexControls from "./components/PokedexControls";
import type { FilterMode, SeriesOrder, SortMode } from "./components/PokedexControls";
import SetGrid from "./components/SetGrid";
import { api, listSets, searchCards } from "../../lib/api";
import { CANON_RARITIES, canonRarity, SERIES_PREFIX_YEAR } from "./components/utils";
import type { CanonRarity, CardRow, SetMeta } from "./components/utils";
import { BookOpen } from "lucide-react";

type SetRow = { id: string; name: string; series: string; release_date?: string | null };
type InvRow = { inventory: { id: number; user_id: number; card_id: string }; card: { id: string; set_id: string } | null };

export default function PokedexTab({
  userId,
  onOpenDetails,
  onAddToInventory,
  onAddToDeck,
  onAddToWishlist,
}: {
  userId: number;
  onOpenDetails: (cardId: string) => void;
  onAddToInventory?: (cardId: string) => void | Promise<void>;
  onAddToDeck?: (cardId: string) => void | Promise<void>;
  onAddToWishlist?: (cardId: string) => void | Promise<void>;
}) {
  const { error: toastError } = useToast();

  // Sets & series
  const [sets, setSets] = useState<SetRow[]>([]);
  const [seriesOrder, setSeriesOrder] = useState<SeriesOrder>("asc");
  const [seriesFilter, setSeriesFilter] = useState<string>("");
  const [setQuery, setSetQuery] = useState<string>("");

  // User inventory
  const [ownedIds, setOwnedIds] = useState<Set<string>>(new Set());
  const [invLoading, setInvLoading] = useState(false);

  // UI prefs
  const [expandedSetId, setExpandedSetId] = useState<string | null>(null);
  const [filterMode, setFilterMode] = useState<FilterMode>("all");
  const [rarityFilter, setRarityFilter] = useState<CanonRarity | "">("");
  const [sortMode, setSortMode] = useState<SortMode>("evoAsc");

  // Per-set cache
  const [metaBySet, setMetaBySet] = useState<Record<string, SetMeta>>({});

  // Load sets once
  useEffect(() => {
    let cancelled = false;
    listSets()
      .then((rows) => !cancelled && setSets(rows))
      .catch((e) => !cancelled && toastError(e instanceof Error ? e.message : String(e)));
    return () => { cancelled = true; };
  }, [toastError]);

  // Load inventory → ownedIds Set
  useEffect(() => {
    let cancelled = false;
    setInvLoading(true);
    api<InvRow[]>(`/inventory/with_cards?user_id=${userId}`)
      .then((rows) => {
        if (cancelled) return;
        const ids = new Set<string>();
        for (const r of rows ?? []) {
          const cid = r.card?.id ?? r.inventory.card_id;
          if (cid) ids.add(cid);
        }
        setOwnedIds(ids);
      })
      .catch((e) => !cancelled && toastError(e instanceof Error ? e.message : String(e)))
      .finally(() => !cancelled && setInvLoading(false));
    return () => { cancelled = true; };
  }, [userId, toastError]);

  // Chronological series list (uses release_date or set-id prefix heuristic)
  const seriesTimeline = useMemo(() => {
    const seriesEarliest: Record<string, number> = {};
    for (const s of sets) {
      let epoch: number | null = null;
      if (s.release_date) {
        const t = Date.parse(s.release_date);
        if (!Number.isNaN(t)) epoch = t;
      }
      if (epoch == null) {
        const m = String(s.id).toLowerCase().match(/^[a-z]+/);
        const year = m?.[0] ? SERIES_PREFIX_YEAR[m[0]] : undefined;
        if (year) epoch = Date.UTC(year, 0, 1);
      }
      if (epoch == null) epoch = 0;
      seriesEarliest[s.series] = seriesEarliest[s.series] == null ? epoch : Math.min(seriesEarliest[s.series], epoch);
    }
    const uniq = Array.from(new Set(sets.map((x) => x.series)));
    uniq.sort((a, b) => {
      const ea = seriesEarliest[a] ?? 0, eb = seriesEarliest[b] ?? 0;
      if (ea !== eb) return ea - eb;
      return a.localeCompare(b);
    });
    return uniq;
  }, [sets]);

  const orderedSeries = useMemo(
    () => (seriesOrder === "asc" ? seriesTimeline : [...seriesTimeline].reverse()),
    [seriesTimeline, seriesOrder]
  );

  // Filter + order visible sets
  const visibleSets = useMemo(() => {
    const q = setQuery.trim().toLowerCase();
    return sets
      .filter((s) => {
        if (seriesFilter && s.series !== seriesFilter) return false;
        if (!q) return true;
        return s.name.toLowerCase().includes(q) || s.id.toLowerCase().includes(q) || s.series.toLowerCase().includes(q);
      })
      .sort((a, b) => {
        const ia = orderedSeries.indexOf(a.series);
        const ib = orderedSeries.indexOf(b.series);
        if (ia !== ib) return ia - ib;
        return a.id.localeCompare(b.id, undefined, { numeric: true, sensitivity: "base" });
      });
  }, [sets, seriesFilter, setQuery, orderedSeries]);

  // Available rarities from loaded cards (prefer expanded set)
  const availableRarities: CanonRarity[] = useMemo(() => {
    const bucket = new Set<CanonRarity>();
    const scan = (rows: CardRow[]) => rows.forEach((c) => bucket.add(canonRarity(c.rarity)));
    if (expandedSetId && metaBySet[expandedSetId]?.items?.length) scan(metaBySet[expandedSetId].items);
    else for (const k of Object.keys(metaBySet)) scan(metaBySet[k].items || []);
    const sorted = Array.from(bucket).sort(
      (a, b) => (CANON_RARITIES.indexOf(a) ?? 999) - (CANON_RARITIES.indexOf(b) ?? 999)
    );
    return sorted.length ? sorted : [...CANON_RARITIES];
  }, [expandedSetId, metaBySet]);

  // Per-set meta management
  function initSetMeta(setId: string) {
    setMetaBySet((m) => (m[setId] ? m : { ...m, [setId]: { total: null, items: [], loading: false, lastLoadedOffset: 0 } }));
  }

  async function loadSetCards(setId: string, batchSize = 200) {
    initSetMeta(setId);
    setMetaBySet((m) => ({ ...m, [setId]: { ...(m[setId] as SetMeta), loading: true } }));
    try {
      const meta = metaBySet[setId] ?? { total: null, items: [], loading: false, lastLoadedOffset: 0 };
      let items = meta.items.slice();
      let total = meta.total;
      let offset = meta.lastLoadedOffset;

      if (total == null) {
        const head = await searchCards({ set_id: setId, limit: 1, offset: 0 });
        total = head.total ?? 0;
      }

      const remaining = Math.max(0, (total ?? 0) - items.length);
      const toFetch = Math.min(remaining, batchSize);

      if (toFetch > 0) {
        const res = await searchCards({ set_id: setId, limit: toFetch, offset });
        items = items.concat(res.items || []);
        offset = items.length;
        total = res.total ?? total ?? items.length;
      }

      setMetaBySet((m) => ({ ...m, [setId]: { total, items, loading: false, lastLoadedOffset: offset } }));
    } catch (e) {
      setMetaBySet((m) => ({ ...m, [setId]: { ...(m[setId] as SetMeta), loading: false } }));
      toastError(e instanceof Error ? e.message : String(e));
    }
  }

  function toggleExpand(setId: string) {
    if (expandedSetId === setId) { setExpandedSetId(null); return; }
    setExpandedSetId(setId);
    const meta = metaBySet[setId];
    if (!meta || (meta.total == null || meta.items.length < (meta.total || 0))) void loadSetCards(setId);
  }

  function ownedCountForSet(setId: string) {
    const meta = metaBySet[setId];
    if (meta?.items?.length) return meta.items.reduce((n, c) => n + (ownedIds.has(c.id) ? 1 : 0), 0);
    let approx = 0; for (const id of ownedIds) if (id.startsWith(`${setId}-`)) approx++;
    return approx;
  }

  return (
    <Section
      title="Pokédex"
      icon={<BookOpen className="w-5 h-5 text-indigo-600" />}
      subtitle="Browse sets, track what you own, filter by rarity, and sort by stage/evolution."
    >
      <PokedexControls
        setQuery={setQuery} onSetQuery={setSetQuery}
        seriesOptions={seriesOrder === "asc" ? [...orderedSeries] : [...orderedSeries]} // ordered already
        seriesFilter={seriesFilter} onSeriesFilter={setSeriesFilter}
        seriesOrder={seriesOrder} onToggleSeriesOrder={() => setSeriesOrder((o) => (o === "asc" ? "desc" : "asc"))}
        filterMode={filterMode} onFilterMode={setFilterMode}
        rarityFilter={rarityFilter} onRarityFilter={setRarityFilter} rarityOptions={availableRarities}
        sortMode={sortMode} onSortMode={setSortMode}
      />

      {invLoading && <div className="text-sm text-slate-600 mb-2">Loading your inventory…</div>}

      <div className="grid gap-3">
        {visibleSets.map((s) => {
          const meta = metaBySet[s.id];
          const total = meta?.total ?? null;
          const owned = ownedCountForSet(s.id);
          const progress = total ? Math.min(100, Math.round((owned / total) * 100)) : null;
          const isOpen = expandedSetId === s.id;

          return (
            <div key={s.id} className="rounded-2xl border bg-white p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <div className="font-semibold truncate">
                    {s.name} <span className="text-slate-400 font-normal">({s.id})</span>
                  </div>
                  <div className="text-xs text-slate-500">{s.series}</div>
                </div>

                <div className="shrink-0 text-sm text-slate-700">
                  {total == null ? <span>{owned} / ?</span> : <span>{owned} / {total} {progress !== null ? `• ${progress}%` : ""}</span>}
                </div>

                <button className="px-3 py-2 rounded-xl border bg-white hover:bg-slate-50" onClick={() => toggleExpand(s.id)}>
                  {isOpen ? "Hide" : "View"}
                </button>
              </div>

              {total !== null && (
                <div className="mt-2 h-2 w-full rounded-full bg-slate-100 overflow-hidden">
                  <div
                    className="h-full bg-indigo-500"
                    style={{ width: `${Math.max(0, Math.min(100, (owned / Math.max(1, total)) * 100))}%` }}
                  />
                </div>
              )}

              {isOpen && (
                <SetGrid
                  meta={meta}
                  loadMore={() => loadSetCards(s.id)}
                  ownedIds={ownedIds}
                  filterMode={filterMode}
                  rarityFilter={rarityFilter}
                  sortMode={sortMode}
                  onOpenDetails={onOpenDetails}
                  onAddToInventory={onAddToInventory}
                  onAddToDeck={onAddToDeck}
                  onAddToWishlist={onAddToWishlist}
                />
              )}
            </div>
          );
        })}
      </div>
    </Section>
  );
}
