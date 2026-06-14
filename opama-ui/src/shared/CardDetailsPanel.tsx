/**
 * CardDetailsPanel (modal)
 * -----------------------
 * Shows rich details for a card with quick actions:
 *  - Add to Inventory / Deck / Wish List / Mark for Trade
 *  - (optional) Find on eBay
 *
 * Drop-in improvements:
 * - Proper dialog semantics (role + aria-labelledby)
 * - Escape to close, click-outside to close
 * - Basic focus management: trap tab within the dialog & restore focus to opener
 * - Uses shared <Button> atom for consistency
 * - Optional `autoCloseOnAction` to close after invoking an action (default: false)
 */

import React, { useEffect, useMemo, useRef, useState } from "react";
import Button from "./atoms/Button";

export interface CardDetailsPanelProps {
  apiBase: string;
  cardId: string | null;
  onClose: () => void;
  onAddToInventory?: (cardId: string) => void | Promise<void>;
  onAddToDeck?: (cardId: string) => void | Promise<void>;
  onAddToWishlist?: (cardId: string) => void | Promise<void>;
  onMarkForTrade?: (cardId: string) => void | Promise<void>;
  /** Optional eBay hook (e.g., prefill + switch tab). */
  onFindOnEbay?: (query: string) => void;
  /** Close after an action invokes successfully (default: false). */
  autoCloseOnAction?: boolean;
}

type CardDetails = {
  id: string;
  name: string;
  set_id: string;
  number?: string | null;
  rarity?: string | null;
  types?: string | null;
  subtypes?: string | null;
  hp?: string | null;
  stage?: string | null;
  ability_name?: string | null;
  ability_text?: string | null;
  attack1_name?: string | null;
  attack1_cost?: string | null;
  attack1_text?: string | null;
  attack1_damage?: string | null;
  attack2_name?: string | null;
  attack2_cost?: string | null;
  attack2_text?: string | null;
  attack2_damage?: string | null;
  attack3_name?: string | null;
  attack3_cost?: string | null;
  attack3_text?: string | null;
  attack3_damage?: string | null;
  weaknesses?: string | null;
  resistances?: string | null;
  retreat_cost?: number | null;
  image_small?: string | null;
  image_large?: string | null;
};

async function api<T>(base: string, path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${base}${path}`, init);
  if (!r.ok) throw new Error(await r.text());
  return (await r.json()) as T;
}

export default function CardDetailsPanel({
  apiBase,
  cardId,
  onClose,
  onAddToInventory,
  onAddToDeck,
  onAddToWishlist,
  onMarkForTrade,
  onFindOnEbay,
  autoCloseOnAction = false,
}: CardDetailsPanelProps) {
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [card, setCard] = useState<CardDetails | null>(null);
  const [imgOk, setImgOk] = useState(true);

  // a11y & focus mgmt
  const backdropRef = useRef<HTMLDivElement | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const closeBtnRef = useRef<HTMLButtonElement | null>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  const headingId = "card-details-title";

  // Load details when opening
  useEffect(() => {
    if (!cardId) return;
    setLoading(true);
    setErr(null);
    setCard(null);
    setImgOk(true);
    api<CardDetails>(apiBase, `/cards/${encodeURIComponent(cardId)}`)
      .then(setCard)
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [apiBase, cardId]);

  // Derive image URLs with local-first strategy
  const { imgSmall, imgLarge } = useMemo(() => {
    const setId = card?.set_id?.trim();
    const num = card?.number?.trim();

    // Priority 1: Local images
    if (setId && num) {
      const localUrl = `/img/${setId}_clean/${setId}-${num}.png`;
      return { imgSmall: localUrl, imgLarge: localUrl };
    }

    // Priority 2: Database URLs
    const fromDbSmall = card?.image_small?.trim() || null;
    const fromDbLarge = card?.image_large?.trim() || null;
    if (fromDbSmall || fromDbLarge) {
      return { imgSmall: fromDbSmall ?? fromDbLarge, imgLarge: fromDbLarge ?? fromDbSmall };
    }

    // Priority 3: Remote API fallback
    if (setId && num) {
      const base = `https://images.pokemontcg.io/${setId}/${num}`;
      return { imgSmall: `${base}.png`, imgLarge: `${base}/large.png` };
    }

    return { imgSmall: null as string | null, imgLarge: null as string | null };
  }, [card?.image_small, card?.image_large, card?.set_id, card?.number]);

  // ========== Dialog behavior & focus ==========
  // Remember opener & focus the close button on open
  useEffect(() => {
    if (!cardId) return;
    openerRef.current = (document.activeElement as HTMLElement) ?? null;
    // delay to ensure element exists
    const t = setTimeout(() => closeBtnRef.current?.focus(), 0);
    return () => clearTimeout(t);
  }, [cardId]);

  // Restore focus to opener on close
  const requestClose = () => {
    onClose();
    // next tick to avoid racing the unmount
    setTimeout(() => openerRef.current?.focus?.(), 0);
  };

  // Escape to close; constrain Tab focus inside dialog
  useEffect(() => {
    if (!cardId) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        requestClose();
      } else if (e.key === "Tab" && dialogRef.current) {
        const focusables = dialogRef.current.querySelectorAll<HTMLElement>(
          'a[href],button,textarea,input,select,[tabindex]:not([tabindex="-1"])'
        );
        if (focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        const active = document.activeElement as HTMLElement | null;
        if (e.shiftKey && active === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && active === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [cardId]);

  if (!cardId) return null;

  // Single place to call an action, then optionally close
  async function invoke(fn?: (id: string) => void | Promise<void>) {
    if (!fn || !card) return;
    await Promise.resolve(fn(card.id));
    if (autoCloseOnAction) requestClose();
  }

  return (
    <div
      ref={backdropRef}
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/40 p-0 sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby={headingId}
      onMouseDown={(e) => {
        // close on backdrop click (but not when dragging within the dialog)
        if (e.target === e.currentTarget) requestClose();
      }}
    >
      <div
        ref={dialogRef}
        className="w-full sm:max-w-xl bg-white rounded-t-2xl sm:rounded-2xl shadow-xl border p-4 sm:p-6"
        onMouseDown={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div id={headingId} className="text-lg font-semibold truncate">
              {card?.name ?? cardId}
            </div>
            <div className="text-xs text-slate-500">
              {card?.set_id || "—"} {card?.number ? `• #${card.number}` : ""}
            </div>
          </div>
          <Button
            ref={closeBtnRef}
            variant="ghost"
            className="px-3 py-1.5"
            onClick={requestClose}
            aria-label="Close details"
          >
            Close
          </Button>
        </div>

        {/* Body */}
        <div className="mt-3 flex gap-4">
          {/* Image */}
          <div className="shrink-0">
            <div className="aspect-[3/4] w-40 bg-slate-100 border rounded-xl grid place-items-center overflow-hidden">
              {imgSmall && imgOk ? (
                <a href={imgLarge ?? imgSmall} target="_blank" rel="noreferrer" title="Open large image">
                  <img
                    src={imgSmall}
                    alt={card?.name || "Card image"}
                    className="w-full h-full object-cover"
                    loading="lazy"
                    decoding="async"
                    onError={() => setImgOk(false)}
                  />
                </a>
              ) : (
                <div className="text-[11px] text-slate-500 px-2 text-center">No image available</div>
              )}
            </div>
          </div>

          {/* Details */}
          <div className="grid gap-2 text-sm min-w-0">
            {loading && <div className="text-slate-600">Loading details…</div>}
            {err && <div className="text-rose-600">Error: {err}</div>}

            {card && (
              <>
                <div className="grid sm:grid-cols-2 gap-2">
                  <Field label="Types" value={card.types} />
                  <Field label="Subtypes" value={card.subtypes} />
                  <Field label="HP" value={card.hp} />
                  <Field label="Stage" value={card.stage} />
                  <Field label="Rarity" value={card.rarity} />
                  <Field label="Retreat" value={card.retreat_cost ?? undefined} />
                  <Field label="Weaknesses" value={card.weaknesses} />
                  <Field label="Resistances" value={card.resistances} />
                </div>

                {card.ability_name && (
                  <div className="mt-1">
                    <div className="text-xs text-slate-500">Ability</div>
                    <div className="font-medium">{card.ability_name}</div>
                    <div className="text-slate-700">{card.ability_text}</div>
                  </div>
                )}

                {/* Attacks */}
                <div className="grid gap-2">
                  {[
                    { n: card.attack1_name, dmg: card.attack1_damage, cost: card.attack1_cost, text: card.attack1_text },
                    { n: card.attack2_name, dmg: card.attack2_damage, cost: card.attack2_cost, text: card.attack2_text },
                    { n: card.attack3_name, dmg: card.attack3_damage, cost: card.attack3_cost, text: card.attack3_text },
                  ]
                    .filter((a) => a.n || a.dmg || a.text)
                    .map((a, i) => (
                      <div key={i} className="p-2 rounded-xl border bg-white">
                        <div className="font-medium">
                          {a.n || `Attack ${i + 1}`} {a.dmg ? `• ${a.dmg}` : ""}
                        </div>
                        <div className="text-xs text-slate-500">{a.cost ? `Cost: ${a.cost}` : ""}</div>
                        {a.text && <div className="text-slate-700">{a.text}</div>}
                      </div>
                    ))}
                </div>

                {/* Actions */}
                <div className="mt-3 flex flex-wrap gap-2">
                  {onAddToInventory && (
                    <Button variant="secondary" onClick={() => invoke(onAddToInventory)}>
                      Add to Inventory
                    </Button>
                  )}
                  {onAddToDeck && (
                    <Button onClick={() => invoke(onAddToDeck)}>Add to Deck</Button>
                  )}
                  {onAddToWishlist && (
                    <Button variant="ghost" onClick={() => invoke(onAddToWishlist)}>
                      Add to Wish List
                    </Button>
                  )}
                  {onMarkForTrade && (
                    <Button variant="ghost" onClick={() => invoke(onMarkForTrade)}>
                      Mark for Trade
                    </Button>
                  )}
                  {onFindOnEbay && (
                    <Button
                      variant="secondary"
                      onClick={() =>
                        onFindOnEbay(
                          [card.name, card.set_id, card.number, "Pokemon TCG"]
                            .filter(Boolean)
                            .join(" ")
                            .trim()
                        )
                      }
                    >
                      Find on eBay
                    </Button>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value?: string | number | null }) {
  return (
    <div>
      <div className="text-xs text-slate-500">{label}</div>
      <div>{value ?? "—"}</div>
    </div>
  );
}
