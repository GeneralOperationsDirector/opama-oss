/**
 * CardTile
 * --------
 * Small, reusable card summary tile:
 *  - Thumbnail (lazy) with graceful fallback if missing/broken
 *  - Name + id/number/rarity line
 *  - Optional right-aligned actions slot
 *  - Optional extra info block (e.g., rarity/condition badges)
 *
 * Props
 * - cardLike: minimal card shape (id is required)
 * - onOpenDetails(cardId): invoked when the left area is clicked
 * - right?: ReactNode for action buttons (right column)
 * - extra?: ReactNode for small extra info under the text (e.g., badges)
 * - fallbackId?: string shown when name is missing and you want a friendlier label
 *
 * Notes
 * - `getCardImageUrls` derives images from explicit fields or from the "svX-123" id.
 * - We track broken image state so we can swap to a "No image" placeholder.
 */

import React, { useMemo, useState } from "react";
import { API_BASE } from "../lib/api";

export type CardLike = {
  id: string;
  name?: string | null;
  set_id?: string | null;
  number?: string | null;
  image_small?: string | null;
  image_large?: string | null;
  rarity?: string | null;
  category?: string | null;
};

/** Uploaded asset images are stored as relative `/uploads/...` paths and
 *  must be resolved against the API host before rendering. */
function resolveImageUrl(url: string | null): string | null {
  if (!url) return null;
  return url.startsWith("/") ? `${API_BASE}${url}` : url;
}

/** Best-effort image URL derivation with local-first strategy:
 *  1) Try local images from /img/{set_id}_clean/{set_id}-{number}.png
 *  2) Fall back to explicit DB URLs if present (resolving relative /uploads/ paths)
 *  3) Fall back to remote API URLs
 *  4) Derive set/num from an id like "sv9-12a" if needed
 */
function getCardImageUrls(card: CardLike) {
  let setId = card.set_id?.trim() || null;
  let num = card.number?.trim() || null;

  // Try to parse from card ID if set/number not directly available
  if ((!setId || !num) && card.id?.includes("-")) {
    const [sid, n] = card.id.split("-", 2);
    if (!setId) setId = sid || null;
    if (!num) num = n || null;
  }

  // Priority 1: Local images
  if (setId && num) {
    const localUrl = `/img/${setId}_clean/${setId}-${num}.png`;
    return { small: localUrl, large: localUrl };
  }

  // Priority 2: Database URLs
  const dbSmall = resolveImageUrl(card.image_small?.trim() || null);
  const dbLarge = resolveImageUrl(card.image_large?.trim() || null);
  if (dbSmall || dbLarge) return { small: dbSmall ?? dbLarge, large: dbLarge ?? dbSmall };

  // Priority 3: Remote API fallback
  if (setId && num) {
    const base = `https://images.pokemontcg.io/${setId}/${num}`;
    return { small: `${base}.png`, large: `${base}/large.png` };
  }

  return { small: null as string | null, large: null as string | null };
}

export default function CardTile({
  cardLike,
  onOpenDetails,
  right,
  extra,
  fallbackId,
}: {
  cardLike: CardLike;
  onOpenDetails: (cardId: string) => void;
  right?: React.ReactNode;
  /** Optional small info block rendered under the text (e.g., rarity/condition). */
  extra?: React.ReactNode;
  /** Optional nicer label when name is missing (e.g., when only an id is known). */
  fallbackId?: string;
}) {
  const cid = cardLike.id;
  const { small: derivedSmall } = useMemo(() => getCardImageUrls(cardLike), [cardLike]);
  const [imgOk, setImgOk] = useState<boolean>(!!derivedSmall);

  const title = cardLike.name || fallbackId || cid;

  return (
    <div className="p-3 sm:p-4 border rounded-2xl bg-white flex flex-col sm:grid sm:grid-cols-[1fr_auto] gap-3 sm:gap-4">
      {/* left: image + text */}
      <button
        className="min-w-0 text-left"
        onClick={() => onOpenDetails(cid)}
        title="View details"
        aria-label={`View details for ${title}`}
      >
        <div className="grid grid-cols-[auto,1fr] gap-3 items-start">
          {/* thumb */}
          <div className="shrink-0 w-20 sm:w-28">
            <div className="aspect-[3/4] w-20 sm:w-28 rounded-xl border bg-slate-100 overflow-hidden">
              {imgOk && derivedSmall ? (
                <img
                  src={derivedSmall}
                  alt={title}
                  className="w-full h-full object-cover"
                  loading="lazy"
                  decoding="async"
                  draggable={false}
                  onError={() => setImgOk(false)}
                />
              ) : (
                <div className="h-full grid place-items-center text-[11px] text-slate-500">
                  No image
                </div>
              )}
            </div>
          </div>

          {/* text */}
          <div className="min-w-0 space-y-1">
            <div className="font-medium truncate">{cardLike.name ?? fallbackId ?? cid}</div>
            <div className="text-xs text-slate-500 truncate">
              {cardLike.set_id
                ? `${cardLike.set_id} • ${cid}${cardLike.number ? ` • #${cardLike.number}` : ""}`
                : cardLike.category || cid}
            </div>
            {cardLike.rarity && <div className="text-xs text-slate-500 mt-0.5">{cardLike.rarity}</div>}
            {/* Optional badges/metadata injected by parent */}
            {extra}
          </div>
        </div>
      </button>

      {/* right: actions — scrollable row on mobile, vertical column on sm+ */}
      <div className="flex flex-row flex-nowrap overflow-x-auto gap-1.5 sm:flex-col sm:flex-wrap sm:overflow-x-visible sm:items-end sm:shrink-0 sm:gap-2">{right}</div>
    </div>
  );
}
