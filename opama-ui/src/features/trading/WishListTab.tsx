/**
 * Wish List Tab
 * -------------
 * Lists the user's wished cards (joined with a light Card shape) and lets them:
 *  - open full details
 *  - add to the active deck
 *  - jump to an affiliate eBay search
 *  - remove from the wish list (optimistic update, rollback on error)
 *
 * Notes
 * - Uses the tiny toast system for non-blocking messages.
 * - Keeps per-row "busy" state so buttons disable while removing.
 * - Builds a decent eBay query from name + set_id + number (+ "Pokemon TCG").
 */

import React, { useCallback, useEffect, useState } from "react";
import Section from "../../shared/atoms/Section";
import Button from "../../shared/atoms/Button";
import { Heart, Swords, Trash2, ShoppingCart } from "lucide-react";
import { getWishlist, removeFromWishlist } from "../../lib/api"; // typed helpers
import { epnSearchUrl } from "../../lib/epn";
import CardTile from "../../shared/CardTile";
import { useToast } from "../../shared/Toaster";

type CardLite = {
  id: string;
  name?: string | null;
  set_id?: string | null;
  number?: string | null;
  image_small?: string | null;
  image_large?: string | null;
  rarity?: string | null;
};

type WishRow = {
  wishlist: { id: number; user_id: number; card_id: string; note?: string | null };
  card: CardLite | null;
};

export default function WishListTab({
  userId,
  onOpenDetails,
  onAddToDeck,
  activeDeckName,
}: {
  userId: number;
  onOpenDetails: (cardId: string) => void;
  onAddToDeck: (cardId: string) => Promise<void>;
  activeDeckName?: string | null;
}) {
  const { success, error: toastError } = useToast();

  const [rows, setRows] = useState<WishRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [busyCardId, setBusyCardId] = useState<string | null>(null); // per-row busy flag

  // Load wish list (best-effort)
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getWishlist(userId)
      .then((r) => {
        if (!cancelled) setRows(Array.isArray(r) ? r : []);
      })
      .catch((e) => {
        if (!cancelled) {
          setRows([]);
          toastError(e instanceof Error ? e.message : String(e));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [userId, toastError]);

  // Build an affiliate eBay search URL from a card row
  const openOnEbay = useCallback((card: CardLite | null, fallbackId: string) => {
    const q = [
      card?.name || fallbackId,
      card?.set_id || "",
      card?.number || "",
      "Pokemon TCG",
    ]
      .filter(Boolean)
      .join(" ")
      .trim();
    window.open(epnSearchUrl(q), "_blank", "noopener,noreferrer");
  }, []);

  // Optimistic removal with rollback on failure
  const remove = useCallback(
    async (cardId: string) => {
      const prev = rows;
      setBusyCardId(cardId);
      // optimistic state
      setRows((curr) => curr.filter((x) => (x.card?.id ?? x.wishlist.card_id) !== cardId));

      try {
        await removeFromWishlist(userId, cardId);
        success("Removed from Wish List");
      } catch (e) {
        // rollback
        setRows(prev);
        toastError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusyCardId(null);
      }
    },
    [rows, userId, success, toastError]
  );

  return (
    <Section
      title="Wish List"
      icon={<Heart className="w-5 h-5 text-indigo-600" />}
      subtitle={activeDeckName ? `Adding to: ${activeDeckName}` : "Select a deck to enable Add to Deck"}
    >
      {loading ? (
        <div className="flex items-center gap-2 text-slate-400 py-6">
          <div className="w-4 h-4 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin" />
          <span className="text-sm">Loading…</span>
        </div>
      ) : rows.length === 0 ? (
        <div className="py-12 text-center space-y-2">
          <div className="text-3xl">💝</div>
          <p className="text-slate-600 font-medium">Your wish list is empty</p>
          <p className="text-sm text-slate-400">Browse the catalog and click "Wish" to save cards here</p>
        </div>
      ) : (
        <div className="grid md:grid-cols-2 gap-3 sm:gap-4">
          {rows.map(({ wishlist: wl, card }) => {
            const cid = card?.id ?? wl.card_id;
            const isBusy = busyCardId === cid;

            return (
              <CardTile
                key={wl.id}
                cardLike={{
                  id: cid,
                  name: card?.name,
                  set_id: card?.set_id ?? undefined,
                  number: card?.number ?? undefined,
                  image_small: card?.image_small ?? undefined,
                  image_large: card?.image_large ?? undefined,
                  rarity: card?.rarity ?? undefined,
                }}
                onOpenDetails={onOpenDetails}
                right={
                  <>
                    <Button
                      className="bg-indigo-600"
                      onClick={() => onAddToDeck(cid)}
                      disabled={isBusy || !activeDeckName}
                      title={activeDeckName ? `Add to "${activeDeckName}"` : "Select a deck first"}
                    >
                      <Swords className="w-4 h-4" />
                      <span className="hidden sm:inline">
                        {activeDeckName ? "Add to Deck" : "No Deck"}
                      </span>
                    </Button>

                    {/* eBay (affiliate) */}
                    <Button
                      className="bg-emerald-600"
                      onClick={() => openOnEbay(card, cid)}
                      title="Open affiliate search on eBay"
                      disabled={isBusy}
                    >
                      <ShoppingCart className="w-4 h-4" /> eBay
                    </Button>

                    <button
                      className="px-3 py-2 rounded-xl border text-sm hover:bg-rose-50 inline-flex items-center gap-1 disabled:opacity-60"
                      onClick={() => remove(cid)}
                      title="Remove from Wish List"
                      disabled={isBusy}
                      aria-busy={isBusy}
                      aria-label={`Remove ${card?.name ?? cid} from Wish List`}
                    >
                      <Trash2 className="w-4 h-4" /> Remove
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
