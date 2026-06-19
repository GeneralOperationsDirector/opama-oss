/**
 * Trade Tab
 * ---------
 * Shows the user's "cards to trade" with quick quantity controls and removal.
 *
 * Improvements:
 * - Uses typed API helpers (`getTradeList`, `upsertTradeItem`, `removeTradeItem`)
 * - Optimistic updates with rollback on failure
 * - Per-row busy state to disable controls during network calls
 * - Non-blocking toasts instead of alert()
 */

import React, { useEffect, useState, useCallback } from "react";
import Section from "../../shared/atoms/Section";
import { Repeat, Trash2 } from "lucide-react";
import CardTile from "../../shared/CardTile";
import { useToast } from "../../shared/Toaster";
import { getTradeList, upsertTradeItem, removeTradeItem } from "../../lib/api";
import TradeMatches from "./TradeMatches";

type CardLite = {
  id: string;
  name: string;
  set_id: string;
  number?: string | null;
  image_small?: string | null;
  image_large?: string | null;
  rarity?: string | null;
};

type TradeRow = {
  trade: { id: number; user_id: number; card_id: string; quantity: number; condition?: string | null };
  card: CardLite | null;
};

export default function TradeTab({
  userId,
  onOpenDetails,
}: {
  userId: number;
  onOpenDetails: (cardId: string) => void;
}) {
  const { success, error: toastError } = useToast();

  const [rows, setRows] = useState<TradeRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState<Record<string, boolean>>({}); // card_id -> busy

  // Load trade list
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getTradeList(userId)
      .then((r) => !cancelled && setRows(Array.isArray(r) ? r : []))
      .catch((e) => !cancelled && toastError(e instanceof Error ? e.message : String(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [userId, toastError]);

  // Optimistic setter with rollback
  const setQty = useCallback(
    async (cardId: string, next: number) => {
      if (busy[cardId]) return; // debounce
      const prev = rows;
      setBusy((b) => ({ ...b, [cardId]: true }));

      // optimistic UI update
      if (next <= 0) {
        setRows((curr) => curr.filter((x) => (x.card?.id ?? x.trade.card_id) !== cardId));
      } else {
        setRows((curr) =>
          curr.map((x) =>
            (x.card?.id ?? x.trade.card_id) === cardId
              ? { ...x, trade: { ...x.trade, quantity: next } }
              : x
          )
        );
      }

      try {
        if (next <= 0) {
          await removeTradeItem(userId, cardId);
          success("Removed from trade list");
        } else {
          await upsertTradeItem(userId, cardId, next);
        }
      } catch (e) {
        // rollback on failure
        setRows(prev);
        toastError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy((b) => {
          const { [cardId]: _omit, ...rest } = b;
          return rest;
        });
      }
    },
    [busy, rows, userId, success, toastError]
  );

  return (
    <Section title="Cards to Trade" icon={<Repeat className="w-5 h-5 text-indigo-600" />}>
      <TradeMatches onOpenDetails={onOpenDetails} />
      {loading ? (
        <div className="text-sm text-slate-600">Loading…</div>
      ) : rows.length === 0 ? (
        <div className="text-sm text-slate-600">No cards marked for trade yet.</div>
      ) : (
        <div className="grid md:grid-cols-2 gap-3 sm:gap-4">
          {rows.map(({ trade: t, card }) => {
            const cid = card?.id ?? t.card_id;
            const isBusy = !!busy[cid];
            const cardLike = card ?? ({ id: t.card_id, name: t.card_id, set_id: "" } as CardLite);

            return (
              <CardTile
                key={t.id}
                cardLike={cardLike}
                fallbackId={t.card_id}
                onOpenDetails={onOpenDetails}
                extra={
                  <>
                    {t.condition && <div className="text-xs text-slate-500">Cond: {t.condition}</div>}
                    {card?.rarity && <div className="text-xs text-slate-500">{card.rarity}</div>}
                  </>
                }
                right={
                  <>
                    <div className="flex items-center gap-2">
                      <button
                        className="px-2 py-1 rounded-lg border text-sm hover:bg-slate-50 disabled:opacity-60"
                        onClick={() => setQty(cid, Math.max(0, t.quantity - 1))}
                        aria-label="Decrease quantity"
                        title="Decrease quantity"
                        disabled={isBusy}
                      >
                        –
                      </button>
                      <div className="text-sm w-8 text-center">{t.quantity}</div>
                      <button
                        className="px-2 py-1 rounded-lg border text-sm hover:bg-slate-50 disabled:opacity-60"
                        onClick={() => setQty(cid, t.quantity + 1)}
                        aria-label="Increase quantity"
                        title="Increase quantity"
                        disabled={isBusy}
                      >
                        +
                      </button>
                    </div>

                    <button
                      className="px-3 py-2 rounded-xl border text-sm hover:bg-rose-50 inline-flex items-center gap-1 disabled:opacity-60"
                      onClick={() => setQty(cid, 0)}
                      title="Remove from Trade"
                      disabled={isBusy}
                      aria-busy={isBusy}
                    >
                      <Trash2 className="w-4 h-4" />
                      Remove
                    </button>
                  </>
                }
              />
            );
          })}
        </div>
      )}
    </Section>
  );
}
