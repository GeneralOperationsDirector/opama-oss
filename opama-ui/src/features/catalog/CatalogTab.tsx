/**
 * Catalog Tab
 * -----------
 * - Browse/search the full card catalog (name + optional set filter)
 * - Import a set CSV (id/name/series + file)
 * - Quick actions per card: Own, Add to Deck, Add to Wish List
 *
 * Notes
 * - Uses small loading flags for sets & search results
 * - Returns 100 items per page; "Next" disables when at the end
 * - Replaces alert() with non-blocking toasts
 */

import React, { useEffect, useMemo, useRef, useState } from "react";
import { Upload, Search as SearchIcon, Swords, Heart } from "lucide-react";
import Section from "../../shared/atoms/Section";
import TextInput from "../../shared/atoms/TextInput";
import Select from "../../shared/atoms/Select";
import Button from "../../shared/atoms/Button";
import { API_BASE, api } from "../../lib/api";
import type { CardRow, SetRow } from "../../types";
import CardTile from "../../shared/CardTile";
import { useToast } from "../../shared/Toaster";
import AddToShowcaseButton from "../showcase/AddToShowcaseButton";
import AddToInventoryButton from "./AddToInventoryButton";

export default function CatalogTab({
  userId,
  onAddToInventory,
  onAddCardToDeck,
  onOpenDetails,
  onAddToWishlist,
}: {
  userId: number;
  onAddToInventory: (cardId: string, quantity?: number) => void | Promise<void>;
  onAddCardToDeck: (cardId: string) => void | Promise<void>;
  onOpenDetails: (cardId: string) => void;
  onAddToWishlist?: (cardId: string) => void | Promise<void>;
}) {
  const { success, error: toastError } = useToast();

  // ------------ Sets state ------------
  const [sets, setSets] = useState<SetRow[]>([]);
  const [setsLoading, setSetsLoading] = useState(false);
  const [setQuery, setSetQuery] = useState("");
  const [selectedSetId, setSelectedSetId] = useState("");

  // ------------ Cards state ------------
  const [cards, setCards] = useState<CardRow[]>([]);
  const [cardsLoading, setCardsLoading] = useState(false);
  const [inputQ, setInputQ] = useState("");  // raw input value (updates immediately)
  const [q, setQ] = useState("");            // debounced value (triggers API call)
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ------------ Owned inventory map ------------
  const [ownedMap, setOwnedMap] = useState<Record<string, number>>({});

  useEffect(() => {
    if (!userId) return;
    api<{ card_id: string; quantity: number }[]>(`/inventory?user_id=${userId}`)
      .then((items) => {
        const map: Record<string, number> = {};
        for (const item of items) {
          map[item.card_id] = (map[item.card_id] ?? 0) + item.quantity;
        }
        setOwnedMap(map);
      })
      .catch(() => {/* silent — badge is enhancement only */});
  }, [userId]);

  // Filter sets by the text box (client-side)
  const filteredSets = useMemo(() => {
    const s = setQuery.trim().toLowerCase();
    if (!s) return sets;
    return sets.filter(
      (x) =>
        (x.name ?? "").toLowerCase().includes(s) ||
        (x.series ?? "").toLowerCase().includes(s) ||
        (x.id ?? "").toLowerCase().includes(s)
    );
  }, [sets, setQuery]);

  // Load sets (once)
  useEffect(() => {
    let cancelled = false;
    setSetsLoading(true);
    api<SetRow[]>(`/cards/sets`)
      .then((list) => !cancelled && setSets(list))
      .catch((e) => !cancelled && toastError(e instanceof Error ? e.message : String(e)))
      .finally(() => !cancelled && setSetsLoading(false));
    return () => {
      cancelled = true;
    };
  }, [toastError]);

  // Search cards on q/offset/selectedSetId changes
  useEffect(() => {
    let cancelled = false;
    setCardsLoading(true);

    (async () => {
      try {
        // Primary query (by name/id/number, with optional set filter)
        const params = new URLSearchParams();
        params.set("limit", "100");
        params.set("offset", String(offset));
        if (q.trim()) params.set("q", q.trim());
        if (selectedSetId) params.set("set_id", selectedSetId);

        let res = await api<{ total: number; items: CardRow[] }>(`/cards/search?${params.toString()}`);

        // Fallback: if set is selected and total is 0, try prefix search by set_id ("sv10-")
        if (!cancelled && selectedSetId && res.total === 0) {
          const p2 = new URLSearchParams();
          p2.set("limit", "100");
          p2.set("offset", String(offset));
          p2.set("q", q.trim() ? q.trim() : `${selectedSetId}-`);
          res = await api<{ total: number; items: CardRow[] }>(`/cards/search?${p2.toString()}`);
        }

        if (!cancelled) {
          setCards(res.items || []);
          setTotal(Number(res.total || 0));
        }
      } catch (e) {
        if (!cancelled) {
          setCards([]);
          setTotal(0);
          // Soft-fail: we already show empty state; toast the error for visibility
          toastError(e instanceof Error ? e.message : String(e));
        }
      } finally {
        !cancelled && setCardsLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [q, offset, selectedSetId, toastError]);

  // Import a single set CSV (id + name + series + file). Uses raw fetch for multipart.
  async function handleUploadSetCsv(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const file = fd.get("file") as File | null;
    if (!file) return;

    const set_id = String(fd.get("set_id") || "");
    const set_name = String(fd.get("set_name") || "");
    const series = String(fd.get("series") || "");

    try {
      const form = new FormData();
      form.append("file", file);
      const r = await fetch(
        `${API_BASE}/cards/import/set?set_id=${encodeURIComponent(set_id)}&set_name=${encodeURIComponent(
          set_name
        )}&series=${encodeURIComponent(series)}`,
        { method: "POST", body: form }
      );
      if (!r.ok) throw new Error(await r.text());
      const { imported } = await r.json();
      success(`Imported ${imported} cards for ${set_id}`);
      setSets(await api<SetRow[]>(`/cards/sets`));
    } catch (e) {
      toastError(e instanceof Error ? e.message : String(e));
    }
  }

  const atStart = offset === 0;
  const atEnd = offset + 100 >= Math.max(total, cards.length); // guard when total is 0/unknown

  return (
    <>
      <Section title="Import a Set CSV" icon={<Upload className="w-5 h-5 text-indigo-600" />}>
        <form className="grid sm:grid-cols-4 gap-3 items-end" onSubmit={handleUploadSetCsv}>
          <div>
            <label className="text-sm">Set ID</label>
            <TextInput name="set_id" placeholder="e.g., sv9" required />
          </div>
          <div>
            <label className="text-sm">Set Name</label>
            <TextInput name="set_name" placeholder="Journey Together" required />
          </div>
          <div>
            <label className="text-sm">Series</label>
            <TextInput name="series" placeholder="Scarlet &amp; Violet" required />
          </div>
          <div className="sm:col-span-4 flex items-center gap-3">
            <input type="file" name="file" accept=".csv" className="block" required />
            <Button type="submit">Import Set</Button>
          </div>
        </form>
      </Section>

      <Section title="Browse Catalog" icon={<SearchIcon className="w-5 h-5 text-indigo-600" />}>
        <div className="grid sm:grid-cols-3 gap-4">
          {/* name/id/number search */}
          <TextInput
            placeholder="Search cards by name…"
            value={inputQ}
            onChange={(e) => {
              const val = e.target.value;
              setInputQ(val);
              if (debounceRef.current) clearTimeout(debounceRef.current);
              debounceRef.current = setTimeout(() => {
                setOffset(0);
                setQ(val);
              }, 300);
            }}
          />

          <div className="sm:col-span-2 grid grid-cols-1 md:grid-cols-2 gap-3">
            {/* set text search */}
            <div className="flex items-center gap-2 rounded-2xl border px-3 py-2 shadow-sm bg-white/80">
              <SearchIcon className="h-4 w-4 opacity-60" />
              <input
                id="set-search"
                type="text"
                autoComplete="off"
                placeholder="Search sets… e.g., Destined Rivals"
                value={setQuery}
                onChange={(e) => setSetQuery(e.target.value)}
                className="w-full bg-transparent outline-none text-sm"
              />
              {setQuery && (
                <button
                  type="button"
                  onClick={() => setSetQuery("")}
                  className="text-xs opacity-70 hover:opacity-100"
                >
                  Clear
                </button>
              )}
            </div>

            {/* set dropdown */}
            <Select
              value={selectedSetId}
              onChange={(e) => {
                setSelectedSetId(e.target.value);
                setOffset(0);
              }}
            >
              <option value="">— Filter by set —</option>
              {setsLoading ? (
                <option value="" disabled>
                  Loading sets…
                </option>
              ) : (
                filteredSets.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name} ({s.id})
                  </option>
                ))
              )}
            </Select>
          </div>
        </div>

        {/* results */}
        {cardsLoading ? (
          <div className="mt-6 flex flex-col items-center gap-2 text-slate-400 py-8">
            <div className="w-6 h-6 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin" />
            <span className="text-sm">Searching…</span>
          </div>
        ) : cards.length === 0 ? (
          <div className="mt-6 py-16 flex flex-col items-center gap-3 text-center">
            <div className="text-4xl">🔍</div>
            {q.trim() || selectedSetId ? (
              <>
                <p className="text-slate-600 font-medium">
                  No cards found{q.trim() ? ` for "${q.trim()}"` : ""}
                  {selectedSetId ? ` in this set` : ""}
                </p>
                <p className="text-sm text-slate-400">Try a different name, number, or set</p>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => { setInputQ(""); setQ(""); setSelectedSetId(""); setOffset(0); }}
                >
                  Clear filters
                </Button>
              </>
            ) : (
              <>
                <p className="text-slate-600 font-medium">No cards yet</p>
                <p className="text-sm text-slate-400">Import a set CSV above to get started</p>
              </>
            )}
          </div>
        ) : (
          <>
            <div className="mt-4 grid md:grid-cols-2 gap-3 sm:gap-4">
              {cards.map((c) => (
                <CardTile
                  key={c.id}
                  cardLike={{
                    id: c.id,
                    name: c.name,
                    set_id: c.set_id,
                    number: (c as any).number,
                    rarity: (c as any).rarity,
                    image_small: (c as any).image_small,
                    image_large: (c as any).image_large,
                  }}
                  onOpenDetails={onOpenDetails}
                  extra={
                    ownedMap[c.id] ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs font-medium">
                        ✓ Owned ×{ownedMap[c.id]}
                      </span>
                    ) : undefined
                  }
                  right={
                    <>
                      <AddToInventoryButton
                        onAdd={async (qty) => {
                          await (onAddToInventory(c.id, qty) as Promise<void>);
                          setOwnedMap((prev) => ({ ...prev, [c.id]: (prev[c.id] ?? 0) + qty }));
                        }}
                      />
                      <Button className="bg-indigo-600" onClick={() => onAddCardToDeck(c.id)} title="Add to active deck">
                        <Swords className="w-4 h-4" /><span className="hidden sm:inline"> Deck</span>
                      </Button>
                      {onAddToWishlist && (
                        <button
                          className="px-3 py-2 rounded-xl border text-sm hover:bg-slate-50 inline-flex items-center gap-1"
                          onClick={() => onAddToWishlist(c.id)}
                          title="Add to Wish List"
                        >
                          <Heart className="w-4 h-4" /><span className="hidden sm:inline"> Wish</span>
                        </button>
                      )}
                      <AddToShowcaseButton
                        userId={userId}
                        cardId={c.id}
                        size="md"
                        onSuccess={(title) => success(`Added to "${title}"`)}
                        onError={(msg) => toastError(msg)}
                      />
                    </>
                  }
                />
              ))}
            </div>

            {total > 100 && (
              <div className="mt-3 text-sm text-slate-600">
                Showing {cards.length} of {total} (server returns 100 at a time)
              </div>
            )}

            <div className="mt-2 flex gap-2">
              <Button
                className="bg-slate-600 hover:bg-slate-700"
                onClick={() => setOffset((o) => Math.max(0, o - 100))}
                disabled={atStart}
              >
                Prev
              </Button>
              <Button onClick={() => setOffset((o) => o + 100)} disabled={atEnd}>
                Next
              </Button>
            </div>
          </>
        )}
      </Section>
    </>
  );
}
