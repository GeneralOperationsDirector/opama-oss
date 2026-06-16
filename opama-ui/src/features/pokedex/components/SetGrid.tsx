import React, { useMemo } from "react";
import Button from "../../../shared/atoms/Button";
import { canonRarity, canonStage, speciesKey, STAGE_RANK_ASC, STAGE_RANK_DESC, getCardImageUrls } from "./utils";
import type { CanonRarity, CardRow, SetMeta } from "./utils";
import type { FilterMode, SortMode } from "./PokedexControls";

export default function SetGrid({
  meta,
  loadMore,
  ownedIds,
  filterMode,
  rarityFilter,
  sortMode,
  onOpenDetails,
  onAddToInventory,
  onAddToDeck,
  onAddToWishlist,
}: {
  meta?: SetMeta;
  loadMore: () => void;
  ownedIds: Set<string>;
  filterMode: FilterMode;
  rarityFilter: CanonRarity | "";
  sortMode: SortMode;
  onOpenDetails: (cardId: string) => void;
  onAddToInventory?: (cardId: string) => void | Promise<void>;
  onAddToDeck?: (cardId: string) => void | Promise<void>;
  onAddToWishlist?: (cardId: string) => void | Promise<void>;
}) {
  if (!meta) return <div className="mt-3 text-sm text-slate-600">Loading cards…</div>;

  const filtered = useMemo(() => {
    let rows = meta.items;
    if (filterMode === "missing") rows = rows.filter((c) => !ownedIds.has(c.id));
    if (filterMode === "owned") rows = rows.filter((c) => ownedIds.has(c.id));
    if (rarityFilter) rows = rows.filter((c) => canonRarity(c.rarity) === rarityFilter);
    return rows;
  }, [meta.items, ownedIds, filterMode, rarityFilter]);

  const sorted = useMemo(() => {
    if (sortMode === "set") return filtered;

    // stage-only
    if (sortMode === "stageAsc" || sortMode === "stageDesc") {
      const rank = sortMode === "stageAsc" ? STAGE_RANK_ASC : STAGE_RANK_DESC;
      const parseNum = (n?: string | null) => {
        const m = n ? String(n).match(/\d+/) : null;
        return m ? parseInt(m[0], 10) : Number.POSITIVE_INFINITY;
      };
      return [...filtered].sort((a, b) => {
        const ra = rank[canonStage(a)], rb = rank[canonStage(b)];
        if (ra !== rb) return ra - rb;
        const na = parseNum(a.number), nb = parseNum(b.number);
        if (na !== nb) return na - nb;
        return (a.name || a.id).localeCompare(b.name || b.id, undefined, { numeric: true, sensitivity: "base" });
      });
    }

    // evolution grouping
    const asc = sortMode === "evoAsc";
    const rank = asc ? STAGE_RANK_ASC : STAGE_RANK_DESC;
    const fam = (x: CardRow) => speciesKey(x.name);
    const parseNum = (n?: string | null) => {
      const m = n ? String(n).match(/\d+/) : null;
      return m ? parseInt(m[0], 10) : Number.POSITIVE_INFINITY;
    };

    return [...filtered].sort((a, b) => {
      const fa = fam(a), fb = fam(b);
      if (fa !== fb) return fa.localeCompare(fb, undefined, { sensitivity: "base" });

      const ra = rank[canonStage(a)], rb = rank[canonStage(b)];
      if (ra !== rb) return ra - rb;

      const na = parseNum(a.number), nb = parseNum(b.number);
      if (na !== nb) return na - nb;
      return (a.name || a.id).localeCompare(b.name || b.id, undefined, { numeric: true, sensitivity: "base" });
    });
  }, [filtered, sortMode]);

  return (
    <div className="mt-3">
      {meta.loading && meta.items.length === 0 ? (
        <div className="text-sm text-slate-600">Loading cards…</div>
      ) : (
        <>
          <div className="grid sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
            {sorted.map((c) => {
              const owned = ownedIds.has(c.id);
              const { small } = getCardImageUrls(c);
              return (
                <article key={c.id} className="group rounded-xl border p-2 bg-white">
                  <button
                    className="w-full aspect-[3/4] rounded-lg overflow-hidden border relative"
                    onClick={() => onOpenDetails(c.id)}
                    title={`${c.name} • ${c.id}`}
                    aria-label={`Open details for ${c.name}`}
                  >
                    {small ? (
                      <img
                        src={small}
                        alt={c.name}
                        className={`w-full h-full object-cover transition ${owned ? "" : "opacity-40"}`}
                        loading="lazy"
                        decoding="async"
                      />
                    ) : (
                      <div className={`w-full h-full grid place-items-center text-[11px] ${owned ? "text-slate-500" : "text-slate-400"}`}>
                        No image
                      </div>
                    )}
                    {owned && (
                      <span className="absolute top-1.5 right-1.5 inline-flex items-center gap-1 rounded-full bg-emerald-600 text-white text-[10px] px-1.5 py-0.5">
                        ✓ Owned
                      </span>
                    )}
                  </button>

                  <div className="mt-2 min-w-0">
                    <div className="text-sm font-medium truncate" title={c.name}>{c.name}</div>
                    <div className="text-xs text-slate-500 truncate" title={`${c.set_id} • ${c.id}${c.number ? ` • #${c.number}` : ""}`}>
                      {c.set_id} • {c.id}{c.number ? ` • #${c.number}` : ""}
                    </div>
                    {c.rarity && <div className="text-[11px] text-slate-500 mt-0.5">{canonRarity(c.rarity)}</div>}
                  </div>

                  <div className="mt-1 flex flex-wrap gap-1">
                    {!owned && onAddToInventory && (
                      <button className="px-2 py-1 rounded-lg border text-[12px] hover:bg-slate-50" onClick={() => onAddToInventory(c.id)}>
                        Own
                      </button>
                    )}
                    {onAddToDeck && (
                      <button className="px-2 py-1 rounded-lg border text-[12px] hover:bg-slate-50" onClick={() => onAddToDeck(c.id)}>
                        Deck
                      </button>
                    )}
                    {onAddToWishlist && (
                      <button className="px-2 py-1 rounded-lg border text-[12px] hover:bg-slate-50" onClick={() => onAddToWishlist(c.id)}>
                        Wish
                      </button>
                    )}
                  </div>
                </article>
              );
            })}
          </div>

          {meta.total !== null && meta.items.length < meta.total && (
            <div className="mt-3">
              <Button onClick={loadMore} loading={!!meta.loading}>Load more</Button>
              <span className="ml-2 text-xs text-slate-500">{meta.items.length} / {meta.total} loaded</span>
            </div>
          )}

          {meta.total == null && (
            <div className="mt-3">
              <Button onClick={loadMore} loading={!!meta.loading}>Load set stats</Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
