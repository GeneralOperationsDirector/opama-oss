/**
 * Inventory Tab
 * -------------
 * Browse and filter the user's owned printings; quick actions to:
 *  - open details
 *  - add to the active deck
 *  - add to wish list
 *  - mark for trade
 *  - tweak inventory quantities (optimistic, with rollback)
 *
 * UX upgrades:
 * - Non-blocking toasts instead of alert()
 * - Per-row "busy" state while mutating (buttons disable)
 * - Optimistic updates for +/-/delete with rollback on error
 * - Lots of inline comments, tiny helpers for parsing/sorting/filtering
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import Section from "../../shared/atoms/Section";
import Select from "../../shared/atoms/Select";
import Button from "../../shared/atoms/Button";
import { Package, Search as SearchIcon, Swords, Plus, Heart, Repeat, Filter, X } from "lucide-react";
import { api } from "../../lib/api";
import type { Deck, InvRow } from "../../types";
import CardTile from "../../shared/CardTile";
import { useToast } from "../../shared/Toaster";
import AddToShowcaseButton from "../showcase/AddToShowcaseButton";

// Local "shape" CardTile accepts (keeps this file self-contained)
type CardLike = {
  id: string;
  name?: string | null;
  set_id?: string | null;
  number?: string | null;
  image_small?: string | null;
  image_large?: string | null;
  rarity?: string | null;
};

export default function InventoryTab({
  userId,
  decks,
  activeDeckId,
  refreshDeck,
  createDeck,
  addCardToDeck,
  onOpenDetails,
  onAddToWishlist,
  onMarkForTrade,
}: {
  userId: number;
  decks: Deck[];
  activeDeckId?: number;
  refreshDeck: (id: number) => Promise<void>;
  createDeck: () => Promise<void>;
  addCardToDeck: (cardId: string) => Promise<void>;
  onOpenDetails: (cardId: string) => void;
  onAddToWishlist: (cardId: string) => void | Promise<void>;
  onMarkForTrade: (cardId: string) => void | Promise<void>;
}) {
  const { success, error: toastError } = useToast();

  const [inventory, setInventory] = useState<InvRow[]>([]);
  const [invQuery, setInvQuery] = useState("");
  const [invLoading, setInvLoading] = useState(false);
  const [busyByItem, setBusyByItem] = useState<Record<number, boolean>>({}); // inventory.id -> busy

  type SortKey = "name" | "set" | "series" | "quantity" | "rarity" | "type" | "stage" | "value";
  type SortDir = "asc" | "desc";
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  const [seriesBySet, setSeriesBySet] = useState<Map<string, string>>(new Map());
  const [filterSeries, setFilterSeries] = useState<string>("");
  const [filterTypes, setFilterTypes] = useState<string[]>([]);
  const [filterStages, setFilterStages] = useState<string[]>([]);
  const [filterSubtypes, setFilterSubtypes] = useState<string[]>([]);
  const [hpMin, setHpMin] = useState<number | "">("");
  const [hpMax, setHpMax] = useState<number | "">("");
  const [retreatMax, setRetreatMax] = useState<number | "">("");
  const [hasAbility, setHasAbility] = useState<boolean>(false);
  const [minTotalDamage, setMinTotalDamage] = useState<number | "">("");

  // ---------- helpers ----------
  const STAGE_ORDER = [
    "Basic",
    "Restored",
    "Stage 1",
    "Stage 2",
    "V",
    "VMAX",
    "VSTAR",
    "ex",
    "ACE SPEC",
    "Special",
  ]; // a loose ordering that still sorts recognizably

  function toInt(x?: string | null): number {
    if (x == null) return NaN;
    const m = String(x).match(/\d+/);
    return m ? parseInt(m[0], 10) : NaN;
  }

  function totalDamage(card: InvRow["card"]): number {
    if (!card) return 0;
    const vals = [card.attack1_damage, card.attack2_damage, card.attack3_damage]
      .map((v) => toInt(v ?? null))
      .filter((n) => !isNaN(n));
    return vals.reduce((a, b) => a + b, 0);
  }

  function detectStage(card?: InvRow["card"] | null): string {
    if (!card) return "";
    const subs = (card.subtypes || "") as string;
    const pieces = subs.split(",").map((s) => s.trim());
    // prefer canonical stages when present
    const found = pieces.find((p) => STAGE_ORDER.includes(p));
    return found || pieces.find((p) => /Stage\s*\d/i.test(p)) || pieces.find((p) => /Basic/i.test(p)) || "";
  }

  function primaryType(card?: InvRow["card"] | null): string {
    if (!card) return "";
    const types = (card.types || "") as string;
    const t = types.split(",").map((s) => s.trim()).filter(Boolean);
    return t[0] || "";
  }

  // ---------- effects ----------
  // Load set->series map (used by the "Series" filter and display badge)
  useEffect(() => {
    api<{ id: string; name: string; series: string }[]>(`/cards/sets`).then((sets) => {
      const m = new Map<string, string>();
      for (const s of sets) m.set(s.id, s.series);
      setSeriesBySet(m);
    });
  }, []);

  // Load user's inventory (with joined Card rows)
  useEffect(() => {
    let cancelled = false;
    setInvLoading(true);
    api<InvRow[]>(`/inventory/with_cards?user_id=${userId}`)
      .then((rows) => {
        if (!cancelled) setInventory(Array.isArray(rows) ? rows : []);
      })
      .catch((e) => {
        if (!cancelled) toastError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setInvLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [userId, toastError]);

  // ---------- mutations (optimistic) ----------
  async function patchInventoryQuantity(itemId: number, delta: number) {
    return api<{ deleted: boolean; item?: { id: number; quantity: number } }>(`/inventory/${itemId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ quantity_delta: delta }),
    });
  }
  async function deleteInventoryItem(itemId: number) {
    await api<{ ok: boolean }>(`/inventory/${itemId}`, { method: "DELETE" });
  }

  const setBusy = useCallback((id: number, on: boolean) => {
    setBusyByItem((m) => (on ? { ...m, [id]: true } : Object.fromEntries(Object.entries(m).filter(([k]) => Number(k) !== id))));
  }, []);

  const decQty = useCallback(
    async (itId: number) => {
      if (busyByItem[itId]) return;
      setBusy(itId, true);
      const prev = inventory;
      // optimistic UI
      setInventory((rows) =>
        rows.flatMap((r) =>
          r.inventory.id === itId
            ? r.inventory.quantity <= 1
              ? [] // if it goes to 0, drop the row optimistically
              : [{ ...r, inventory: { ...r.inventory, quantity: r.inventory.quantity - 1 } }]
            : [r]
        )
      );
      try {
        const res = await patchInventoryQuantity(itId, -1);
        if (res.deleted) {
          // already removed above; nothing else to do
        }
      } catch (e) {
        setInventory(prev); // rollback
        toastError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(itId, false);
      }
    },
    [busyByItem, inventory, setBusy, toastError]
  );

  const incQty = useCallback(
    async (itId: number) => {
      if (busyByItem[itId]) return;
      setBusy(itId, true);
      const prev = inventory;
      setInventory((rows) =>
        rows.map((r) => (r.inventory.id === itId ? { ...r, inventory: { ...r.inventory, quantity: r.inventory.quantity + 1 } } : r))
      );
      try {
        await patchInventoryQuantity(itId, +1);
      } catch (e) {
        setInventory(prev);
        toastError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(itId, false);
      }
    },
    [busyByItem, inventory, setBusy, toastError]
  );

  const removeItem = useCallback(
    async (itId: number) => {
      if (busyByItem[itId]) return;
      setBusy(itId, true);
      const prev = inventory;
      setInventory((rows) => rows.filter((r) => r.inventory.id !== itId)); // optimistic
      try {
        await deleteInventoryItem(itId);
        success("Removed from inventory");
      } catch (e) {
        setInventory(prev); // rollback
        toastError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(itId, false);
      }
    },
    [busyByItem, inventory, setBusy, success, toastError]
  );

  // ---------- search / options ----------
  const filteredInventory = useMemo(() => {
    const q = invQuery.trim().toLowerCase();
    if (!q) return inventory;
    return inventory.filter(({ inventory: it, card }) => {
      const name = (card?.name || "").toLowerCase();
      const setId = (card?.set_id || "").toLowerCase();
      const number = (card?.number || "").toLowerCase();
      const cid = (card?.id || it.card_id || "").toLowerCase();
      return name.includes(q) || setId.includes(q) || number.includes(q) || cid.includes(q);
    });
  }, [inventory, invQuery]);

  const seriesOptions = useMemo(() => {
    const s = new Set<string>();
    for (const row of filteredInventory) {
      const ser = seriesBySet.get(row.card?.set_id ?? "");
      if (ser) s.add(ser);
    }
    return Array.from(s).sort();
  }, [filteredInventory, seriesBySet]);

  const typeOptions = useMemo(() => {
    const s = new Set<string>();
    for (const row of filteredInventory) {
      const types = (row.card?.types || "") as string;
      if (types) types.split(",").map((t) => t.trim()).filter(Boolean).forEach((t) => s.add(t));
    }
    return Array.from(s).sort();
  }, [filteredInventory]);

  const subtypeOptions = useMemo(() => {
    const s = new Set<string>();
    for (const row of filteredInventory) {
      const subs = (row.card?.subtypes || "") as string;
      if (subs) subs.split(",").map((t) => t.trim()).filter(Boolean).forEach((t) => s.add(t));
    }
    return Array.from(s).sort();
  }, [filteredInventory]);

  const STAGE_CHOICES = useMemo(() => {
    // Only keep values that look like stages, and sort with STAGE_ORDER when known
    const stageLike = new Set<string>();
    for (const st of subtypeOptions) {
      if (STAGE_ORDER.includes(st) || /^(Basic|Stage\s*\d|VSTAR|VMAX|ex)$/i.test(st)) stageLike.add(st);
    }
    return Array.from(stageLike).sort((a, b) => {
      const ai = STAGE_ORDER.indexOf(a);
      const bi = STAGE_ORDER.indexOf(b);
      if (ai === -1 && bi === -1) return a.localeCompare(b);
      if (ai === -1) return 1;
      if (bi === -1) return -1;
      return ai - bi;
    });
  }, [subtypeOptions]);

  // ---------- visible list (filters + sort) ----------
  const visibleInventory = useMemo(() => {
    let rows = filteredInventory.filter(({ card }) => {
      if (filterSeries) {
        const ser = seriesBySet.get(card?.set_id ?? "");
        if (ser !== filterSeries) return false;
      }
      if (filterTypes.length) {
        const types = (card?.types || "").split(",").map((x) => x.trim()).filter(Boolean);
        if (!filterTypes.every((t) => types.includes(t))) return false;
      }
      if (filterStages.length) {
        const detected = detectStage(card);
        if (!detected || !filterStages.includes(detected)) return false;
      }
      if (filterSubtypes.length) {
        const subs = (card?.subtypes || "").split(",").map((x) => x.trim()).filter(Boolean);
        if (!filterSubtypes.every((t) => subs.includes(t))) return false;
      }
      if (hpMin !== "" || hpMax !== "") {
        const hp = toInt(card?.hp ?? null);
        if (hpMin !== "" && !isNaN(hp) && hp < Number(hpMin)) return false;
        if (hpMax !== "" && !isNaN(hp) && hp > Number(hpMax)) return false;
      }
      if (retreatMax !== "") {
        const rc = card?.retreat_cost ?? null;
        if (rc != null && rc > Number(retreatMax)) return false;
      }
      if (hasAbility && !card?.ability_name) return false;
      if (minTotalDamage !== "" && totalDamage(card) < Number(minTotalDamage)) return false;
      return true;
    });

    // sorting
    rows = rows.slice().sort((a, b) => {
      const get = (r: InvRow) => {
        switch (sortKey) {
          case "name":
            return (r.card?.name || r.inventory.card_id || "").toLowerCase();
          case "set":
            return (r.card?.set_id || "").toLowerCase();
          case "series":
            return (seriesBySet.get(r.card?.set_id ?? "") || "").toLowerCase();
          case "rarity":
            return (r.card?.rarity || "").toLowerCase();
          case "quantity":
            return r.inventory.quantity;
          case "type":
            return primaryType(r.card).toLowerCase();
          case "stage":
            return detectStage(r.card).toLowerCase();
          case "value":
            return r.inventory.purchase_price_per_card || 0;
        }
      };
      const av = get(a);
      const bv = get(b);
      if (typeof av === "number" && typeof bv === "number") return sortDir === "asc" ? av - bv : bv - av;
      const cmp = String(av).localeCompare(String(bv));
      return sortDir === "asc" ? cmp : -cmp;
    });

    return rows;
  }, [
    filteredInventory,
    filterSeries,
    filterTypes,
    filterStages,
    filterSubtypes,
    hpMin,
    hpMax,
    retreatMax,
    hasAbility,
    minTotalDamage,
    sortKey,
    sortDir,
    seriesBySet,
  ]);

  function resetFilters() {
    setFilterSeries("");
    setFilterTypes([]);
    setFilterStages([]);
    setFilterSubtypes([]);
    setHpMin("");
    setHpMax("");
    setRetreatMax("");
    setHasAbility(false);
    setMinTotalDamage("");
  }

  // ---------- render ----------
  return (
    <Section title="Your Inventory" icon={<Package className="w-5 h-5 text-indigo-600" />}>
      {/* deck selector */}
      <div className="mb-3 flex items-center gap-2">
        <Select
          value={activeDeckId ? String(activeDeckId) : ""}
          onChange={(e) => {
            const id = parseInt(e.target.value);
            if (!isNaN(id)) refreshDeck(id);
          }}
        >
          <option value="">— Select a deck —</option>
          {decks.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name} (#{d.id})
            </option>
          ))}
        </Select>
        <Button onClick={createDeck}>
          <Plus className="w-4 h-4" /> New Deck
        </Button>
      </div>

      {/* search */}
      <div className="mb-3">
        <label className="sr-only" htmlFor="inv-search">
          Search inventory
        </label>
        <div className="flex items-center gap-2 rounded-2xl border px-3 py-2 shadow-sm bg-white/80">
          <SearchIcon className="h-4 w-4 opacity-60" />
          <input
            id="inv-search"
            type="text"
            autoComplete="off"
            placeholder="Search inventory… name, set, number, or card id"
            value={invQuery}
            onChange={(e) => setInvQuery(e.target.value)}
            className="w-full bg-transparent outline-none text-sm"
          />
          {invQuery && (
            <button
              type="button"
              onClick={() => setInvQuery("")}
              className="text-xs opacity-70 hover:opacity-100"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* filters & sort */}
      <div className="mb-4 rounded-2xl border bg-white/70 p-3 shadow-sm">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2 text-sm font-medium">
            <Filter className="w-4 h-4" /> Filters
          </div>
          <div className="flex items-center gap-2">
            <label className="text-xs text-slate-600">Sort by</label>
            <Select
              value={`${sortKey}:${sortDir}`}
              onChange={(e) => {
                const [k, d] = e.target.value.split(":") as [SortKey, SortDir];
                setSortKey(k);
                setSortDir(d);
              }}
            >
              {[
                ["name:asc", "Name ↑"],
                ["name:desc", "Name ↓"],
                ["set:asc", "Set ↑"],
                ["set:desc", "Set ↓"],
                ["series:asc", "Series ↑"],
                ["series:desc", "Series ↓"],
                ["type:asc", "Type ↑"],
                ["type:desc", "Type ↓"],
                ["stage:asc", "Stage ↑"],
                ["stage:desc", "Stage ↓"],
                ["rarity:asc", "Rarity ↑"],
                ["rarity:desc", "Rarity ↓"],
                ["quantity:asc", "Qty ↑"],
                ["quantity:desc", "Qty ↓"],
                ["value:desc", "Value ↓ (High to Low)"],
                ["value:asc", "Value ↑ (Low to High)"],
              ].map(([val, label]) => (
                <option key={val} value={val}>
                  {label}
                </option>
              ))}
            </Select>

            <button
              className="text-xs inline-flex items-center gap-1 rounded-lg border px-2 py-1 hover:bg-slate-50"
              onClick={resetFilters}
              title="Reset all filters"
            >
              <X className="w-3 h-3" /> Reset
            </button>
          </div>
        </div>

        {/* row 1: series + type + stage */}
        <div className="grid md:grid-cols-3 gap-3">
          <div>
            <label className="block text-xs text-slate-600 mb-1">Series</label>
            <Select value={filterSeries} onChange={(e) => setFilterSeries(e.target.value)}>
              <option value="">All series</option>
              {seriesOptions.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </Select>
          </div>

          <div>
            <label className="block text-xs text-slate-600 mb-1">Type (Energy)</label>
            <div className="flex flex-wrap gap-2">
              {typeOptions.map((t) => {
                const checked = filterTypes.includes(t);
                return (
                  <label
                    key={t}
                    className={`text-xs inline-flex items-center gap-1 px-2 py-1 rounded-full border cursor-pointer ${
                      checked ? "bg-indigo-50 border-indigo-300" : "bg-white"
                    }`}
                  >
                    <input
                      type="checkbox"
                      className="accent-indigo-600"
                      checked={checked}
                      onChange={(e) => {
                        setFilterTypes((prev) =>
                          e.target.checked ? Array.from(new Set([...prev, t])) : prev.filter((x) => x !== t)
                        );
                      }}
                    />
                    {t}
                  </label>
                );
              })}
            </div>
          </div>

          <div>
            <label className="block text-xs text-slate-600 mb-1">Stage</label>
            <div className="flex flex-wrap gap-2">
              {STAGE_CHOICES.map((st) => {
                const checked = filterStages.includes(st);
                return (
                  <label
                    key={st}
                    className={`text-xs inline-flex items-center gap-1 px-2 py-1 rounded-full border cursor-pointer ${
                      checked ? "bg-indigo-50 border-indigo-300" : "bg-white"
                    }`}
                  >
                    <input
                      type="checkbox"
                      className="accent-indigo-600"
                      checked={checked}
                      onChange={(e) => {
                        setFilterStages((prev) =>
                          e.target.checked ? Array.from(new Set([...prev, st])) : prev.filter((x) => x !== st)
                        );
                      }}
                    />
                    {st}
                  </label>
                );
              })}
            </div>
          </div>
        </div>

        {/* row 2: abilities/hp/retreat/damage */}
        <div className="grid md:grid-cols-4 gap-3 mt-3">
          <div className="flex items-center gap-2">
            <input
              id="hasAbility"
              type="checkbox"
              className="accent-indigo-600"
              checked={hasAbility}
              onChange={(e) => setHasAbility(e.target.checked)}
            />
            <label htmlFor="hasAbility" className="text-sm">
              Has Ability
            </label>
          </div>

          <div className="flex items-center gap-2">
            <label className="text-xs text-slate-600">HP</label>
            <input
              type="number"
              inputMode="numeric"
              min={0}
              className="w-20 rounded-lg border px-2 py-1 text-sm"
              placeholder="min"
              value={hpMin}
              onChange={(e) => setHpMin(e.target.value === "" ? "" : Number(e.target.value))}
            />
            <span className="text-xs">–</span>
            <input
              type="number"
              inputMode="numeric"
              min={0}
              className="w-20 rounded-lg border px-2 py-1 text-sm"
              placeholder="max"
              value={hpMax}
              onChange={(e) => setHpMax(e.target.value === "" ? "" : Number(e.target.value))}
            />
          </div>

          <div className="flex items-center gap-2">
            <label className="text-xs text-slate-600">Retreat ≤</label>
            <input
              type="number"
              inputMode="numeric"
              min={0}
              className="w-24 rounded-lg border px-2 py-1 text-sm"
              placeholder="#"
              value={retreatMax}
              onChange={(e) => setRetreatMax(e.target.value === "" ? "" : Number(e.target.value))}
            />
          </div>

          <div className="flex items-center gap-2">
            <label className="text-xs text-slate-600">Total Damage ≥</label>
            <input
              type="number"
              inputMode="numeric"
              min={0}
              className="w-24 rounded-lg border px-2 py-1 text-sm"
              placeholder="#"
              value={minTotalDamage}
              onChange={(e) => setMinTotalDamage(e.target.value === "" ? "" : Number(e.target.value))}
            />
          </div>
        </div>
      </div>

      {invLoading ? (
        <div className="text-sm text-slate-600">Loading…</div>
      ) : visibleInventory.length === 0 ? (
        <div className="text-sm text-slate-600">No items match. Try a different search/filter.</div>
      ) : (
        <>
          <div className="text-xs text-slate-500 mb-2">
            Showing {visibleInventory.length} of {inventory.length}
          </div>

          <div className="grid md:grid-cols-2 gap-3 sm:gap-4">
            {visibleInventory.map(({ inventory: it, card }) => {
              const cardLike: CardLike = card
                ? {
                    id: card.id,
                    name: card.name,
                    set_id: card.set_id,
                    number: (card as any).number as any,
                    image_small: (card as any).image_small,
                    image_large: (card as any).image_large,
                    rarity: (card as any).rarity,
                  }
                : ({ id: it.card_id, name: it.card_id } as any);

              const cardId = card?.id ?? it.card_id;
              const type = primaryType(card);
              const stage = detectStage(card);
              const series = seriesBySet.get(card?.set_id ?? "");
              const isBusy = !!busyByItem[it.id];

              return (
                <CardTile
                  key={it.id}
                  cardLike={cardLike}
                  onOpenDetails={(id) => onOpenDetails(id)}
                  right={
                    <>
                      {/* badges/info */}
                      <div className="text-right space-y-0.5">
                        {type && (
                          <div className="text-[11px] text-slate-600">
                            Type: <span className="font-medium">{type}</span>
                          </div>
                        )}
                        {stage && (
                          <div className="text-[11px] text-slate-600">
                            Stage: <span className="font-medium">{stage}</span>
                          </div>
                        )}
                        {series && (
                          <div className="text-[11px] text-slate-600">
                            Series: <span className="font-medium">{series}</span>
                          </div>
                        )}
                        {it.condition && <div className="text-xs text-slate-500">Cond: {it.condition}</div>}
                        {it.is_reverse_holo ? <div className="text-[11px] text-indigo-600">Reverse Holo</div> : null}
                      </div>

                      <Button
                        className={`bg-indigo-600 ${!activeDeckId ? "opacity-50 cursor-not-allowed" : ""}`}
                        onClick={() =>
                          activeDeckId ? addCardToDeck(cardId) : toastError("Select or create a deck first (picker above).")
                        }
                        disabled={!activeDeckId || isBusy}
                        title="Add to active deck"
                      >
                        <Swords className="w-4 h-4" /> Deck
                      </Button>

                      <button
                        className="px-3 py-2 rounded-xl border text-sm hover:bg-slate-50 inline-flex items-center gap-1 disabled:opacity-60"
                        onClick={() => onAddToWishlist(cardId)}
                        title="Add to Wish List"
                        disabled={isBusy}
                      >
                        <Heart className="w-4 h-4" /> Wish
                      </button>

                      <button
                        className="px-3 py-2 rounded-xl border text-sm hover:bg-slate-50 inline-flex items-center gap-1 disabled:opacity-60"
                        onClick={() => onMarkForTrade(cardId)}
                        title="Mark for Trade"
                        disabled={isBusy}
                      >
                        <Repeat className="w-4 h-4" /> Trade
                      </button>

                      <AddToShowcaseButton
                        userId={userId}
                        cardId={cardId}
                        size="md"
                        onSuccess={(title) => success(`Added to "${title}"`)}
                        onError={(msg) => toastError(msg)}
                      />

                      <div className="flex items-center gap-2">
                        <button
                          className="px-2 py-1 rounded-lg border text-sm hover:bg-slate-50 disabled:opacity-60"
                          onClick={() => decQty(it.id)}
                          title="Decrease quantity"
                          disabled={isBusy}
                          aria-busy={isBusy}
                        >
                          –
                        </button>

                        <div className="text-sm w-8 text-center">{it.quantity}</div>

                        <button
                          className="px-2 py-1 rounded-lg border text-sm hover:bg-slate-50 disabled:opacity-60"
                          onClick={() => incQty(it.id)}
                          title="Increase quantity"
                          disabled={isBusy}
                          aria-busy={isBusy}
                        >
                          +
                        </button>

                        <button
                          className="ml-1 px-2 py-1 rounded-lg border text-sm hover:bg-rose-50 disabled:opacity-60"
                          onClick={() => removeItem(it.id)}
                          title="Remove item"
                          disabled={isBusy}
                          aria-busy={isBusy}
                        >
                          🗑
                        </button>
                      </div>
                    </>
                  }
                />
              );
            })}
          </div>
        </>
      )}

    </Section>
  );
}
