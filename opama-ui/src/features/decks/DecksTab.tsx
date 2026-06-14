/**
 * Decks Tab
 * ---------
 * - Select / create / rename / delete decks
 * - Inline quantity controls for deck cards
 * - Get quick heuristic suggestions
 *
 * Upgrades:
 * - Non-blocking toasts for success/errors
 * - Per-row busy state on card ops; deck-level busy on rename/delete
 * - Optimistic +/-/remove with rollback on failure
 * - Defensive guards when no active deck is selected
 */

import React, { useCallback, useMemo, useState } from "react";
import Section from "../../shared/atoms/Section";
import Button from "../../shared/atoms/Button";
import Select from "../../shared/atoms/Select";
import { Layers, Sparkles, Plus, Trash2 } from "lucide-react";
import {
  fetchDecksForUser,
  renameDeck,
  deleteDeck,
  patchDeckCard,
  removeDeckCard, // compat alias provided in lib/api
} from "../../lib/api";
import type { Deck, DeckWithCards } from "../../types";
import { useToast } from "../../shared/Toaster";

export default function DecksTab({
  userId,
  decks,
  setDecks,
  activeDeck,
  setActiveDeck,
  activeDeckId,
  setActiveDeckId,
  getSuggestions,
  refreshDeck,
  createDeck,
}: {
  userId: number;
  decks: Deck[];
  setDecks: React.Dispatch<React.SetStateAction<Deck[]>>;
  activeDeck: DeckWithCards | null;
  setActiveDeck: React.Dispatch<React.SetStateAction<DeckWithCards | null>>;
  activeDeckId?: number;
  setActiveDeckId: (id: number | undefined) => void;
  getSuggestions: () => Promise<void>;
  refreshDeck: (id: number) => Promise<void>;
  createDeck: () => Promise<void>;
}) {
  const { success, error: toastError } = useToast();

  // Busy flags
  const [deckBusy, setDeckBusy] = useState<"rename" | "delete" | null>(null);
  const [busyByDeckCard, setBusyByDeckCard] = useState<Record<number, boolean>>({}); // dc.id -> busy

  const hasActive = !!activeDeck && !!activeDeckId;

  // Helper to set/clear busy per deck-card id
  const setLineBusy = useCallback((id: number, on: boolean) => {
    setBusyByDeckCard((m) =>
      on ? { ...m, [id]: true } : Object.fromEntries(Object.entries(m).filter(([k]) => Number(k) !== id))
    );
  }, []);

  // Optimistic decrement
  const decQty = useCallback(
    async (deckId: number, deckCardId: number) => {
      if (busyByDeckCard[deckCardId]) return;
      setLineBusy(deckCardId, true);

      const prev = activeDeck;
      // optimistic UI update
      setActiveDeck((curr) =>
        !curr
          ? curr
          : {
              ...curr,
              cards: curr.cards.flatMap((dc) =>
                dc.id !== deckCardId
                  ? [dc]
                  : dc.quantity <= 1
                  ? [] // drop line at 0
                  : [{ ...dc, quantity: dc.quantity - 1 }]
              ),
            }
      );

      try {
        const res: any = await patchDeckCard(deckId, deckCardId, { quantity_delta: -1 });
        // server may return {deleted:true} — we've already reflected that optimistically
        if (res && res.error) throw new Error(res.error);
      } catch (e) {
        // rollback on failure
        setActiveDeck(prev);
        toastError(e instanceof Error ? e.message : String(e));
      } finally {
        setLineBusy(deckCardId, false);
      }
    },
    [activeDeck, busyByDeckCard, setLineBusy, setActiveDeck, toastError]
  );

  // Optimistic increment
  const incQty = useCallback(
    async (deckId: number, deckCardId: number) => {
      if (busyByDeckCard[deckCardId]) return;
      setLineBusy(deckCardId, true);

      const prev = activeDeck;
      setActiveDeck((curr) =>
        !curr ? curr : { ...curr, cards: curr.cards.map((dc) => (dc.id === deckCardId ? { ...dc, quantity: dc.quantity + 1 } : dc)) }
      );

      try {
        await patchDeckCard(deckId, deckCardId, { quantity_delta: +1 });
      } catch (e) {
        setActiveDeck(prev);
        toastError(e instanceof Error ? e.message : String(e));
      } finally {
        setLineBusy(deckCardId, false);
      }
    },
    [activeDeck, busyByDeckCard, setLineBusy, setActiveDeck, toastError]
  );

  // Optimistic remove line
  const removeLine = useCallback(
    async (deckId: number, deckCardId: number) => {
      if (busyByDeckCard[deckCardId]) return;
      setLineBusy(deckCardId, true);

      const prev = activeDeck;
      setActiveDeck((curr) => (!curr ? curr : { ...curr, cards: curr.cards.filter((dc) => dc.id !== deckCardId) }));

      try {
        await removeDeckCard(deckId, deckCardId);
      } catch (e) {
        setActiveDeck(prev);
        toastError(e instanceof Error ? e.message : String(e));
      } finally {
        setLineBusy(deckCardId, false);
      }
    },
    [activeDeck, busyByDeckCard, setLineBusy, setActiveDeck, toastError]
  );

  // Derived: nice little header for the active deck
  const deckMeta = useMemo(() => {
    if (!activeDeck) return null;
    return {
      name: activeDeck.deck.name,
      format: activeDeck.deck.format || "—",
      count: activeDeck.cards.reduce((n, dc) => n + (dc.quantity || 0), 0),
    };
  }, [activeDeck]);

  return (
    <Section title="Decks" icon={<Layers className="w-5 h-5 text-indigo-600" />}>
      <div className="flex gap-3 items-center mb-3 flex-wrap">
        <Button onClick={createDeck}>
          <Plus className="w-4 h-4" /> New Deck
        </Button>

        <Select
          value={activeDeckId ? String(activeDeckId) : ""}
          onChange={async (e) => {
            const id = parseInt(e.target.value);
            if (!isNaN(id)) await refreshDeck(id);
          }}
        >
          <option value="">— Select a deck —</option>
          {decks.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name} (#{d.id})
            </option>
          ))}
        </Select>

        <Button onClick={getSuggestions} disabled={!hasActive}>
          <Sparkles className="w-4 h-4" /> Get Suggestions
        </Button>

        <Button
          className="bg-slate-600 hover:bg-slate-700 disabled:opacity-60"
          disabled={!hasActive || deckBusy !== null}
          onClick={async () => {
            if (!activeDeckId) {
              toastError("Select a deck first");
              return;
            }
            const newName = prompt("New deck name?", activeDeck?.deck.name || "");
            if (!newName) return;

            setDeckBusy("rename");
            try {
              await renameDeck(activeDeckId, newName);
              await refreshDeck(activeDeckId);
              const list = await fetchDecksForUser(userId);
              setDecks(list);
              success("Deck renamed");
            } catch (e) {
              toastError(e instanceof Error ? e.message : String(e));
            } finally {
              setDeckBusy(null);
            }
          }}
        >
          Rename
        </Button>

        <Button
          className="bg-rose-600 hover:bg-rose-700 disabled:opacity-60"
          disabled={!hasActive || deckBusy !== null}
          onClick={async () => {
            if (!activeDeckId) {
              toastError("Select a deck first");
              return;
            }
            if (!confirm("Delete this deck?")) return;

            setDeckBusy("delete");
            try {
              await deleteDeck(activeDeckId);
              const list = await fetchDecksForUser(userId);
              setDecks(list);
              setActiveDeckId(undefined);
              setActiveDeck(null);
              success("Deck deleted");
            } catch (e) {
              toastError(e instanceof Error ? e.message : String(e));
            } finally {
              setDeckBusy(null);
            }
          }}
        >
          Delete
        </Button>
      </div>

      {activeDeck && (
        <div className="grid md:grid-cols-2 gap-3">
          {/* Summary card */}
          <div className="p-3 border rounded-xl bg-white">
            <div className="font-semibold">{deckMeta?.name}</div>
            <div className="text-xs text-slate-500">
              Format: {deckMeta?.format} • Total cards: {deckMeta?.count}
            </div>
          </div>

          {/* Card list */}
          <div className="p-3 border rounded-xl bg-white">
            <div className="font-semibold mb-2">Cards</div>
            <ul className="text-sm space-y-1 max-h-80 overflow-auto pr-2">
              {activeDeck.cards.map((dc) => {
                const isBusy = !!busyByDeckCard[dc.id];
                return (
                  <li key={dc.id} className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="font-medium truncate">{dc.card?.name ?? dc.card_id}</div>
                      <div className="text-xs text-slate-500 truncate">
                        {dc.card
                          ? `${dc.card.set_id} • ${dc.card.id}${dc.card.number ? ` • #${dc.card.number}` : ""}`
                          : dc.card_id}
                        {dc.role ? ` • ${dc.role}` : ""}
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        className="px-2 py-1 rounded-lg border text-sm hover:bg-slate-50 disabled:opacity-60"
                        onClick={() => hasActive && decQty(activeDeck.deck.id, dc.id)}
                        disabled={!hasActive || isBusy}
                        aria-label="Decrease quantity"
                        aria-busy={isBusy}
                        title="Decrease"
                      >
                        –
                      </button>

                      <div className="text-sm w-8 text-center">{dc.quantity}</div>

                      <button
                        className="px-2 py-1 rounded-lg border text-sm hover:bg-slate-50 disabled:opacity-60"
                        onClick={() => hasActive && incQty(activeDeck.deck.id, dc.id)}
                        disabled={!hasActive || isBusy}
                        aria-label="Increase quantity"
                        aria-busy={isBusy}
                        title="Increase"
                      >
                        +
                      </button>

                      <button
                        className="ml-1 px-2 py-1 rounded-lg border text-sm hover:bg-rose-50 disabled:opacity-60 inline-flex items-center gap-1"
                        onClick={() => hasActive && removeLine(activeDeck.deck.id, dc.id)}
                        disabled={!hasActive || isBusy}
                        aria-label="Remove card"
                        aria-busy={isBusy}
                        title="Remove card"
                      >
                        <Trash2 className="w-4 h-4" />
                        Remove
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      )}
    </Section>
  );
}
