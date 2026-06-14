// Central helper for building Pokémon TCG image URLs
export type Imageable = {
  set_id?: string;
  number?: string | null;
  image_small?: string | null;
  image_large?: string | null;
};

/**
 * Build image URLs with the following priority:
 * 1. Local images from /img/{set_id}_clean/{set_id}-{number}.png
 * 2. Database URLs (image_small, image_large) if present
 * 3. Remote API URLs as final fallback
 */
export function buildImageUrlsFromCard(card?: Imageable | null) {
  const setId = card?.set_id?.trim();
  const num = card?.number?.trim();

  // Priority 1: Try local images first
  if (setId && num) {
    const localUrl = `/img/${setId}_clean/${setId}-${num}.png`;
    return { small: localUrl, large: localUrl };
  }

  // Priority 2: Use database URLs if available
  const dbSmall = card?.image_small?.trim() || null;
  const dbLarge = card?.image_large?.trim() || null;
  if (dbSmall || dbLarge) return { small: dbSmall ?? dbLarge, large: dbLarge ?? dbSmall };

  // Priority 3: Fall back to remote API
  if (setId && num) {
    const base = `https://images.pokemontcg.io/${setId}/${num}`;
    return { small: `${base}.png`, large: `${base}/large.png` };
  }

  return { small: null as string | null, large: null as string | null };
}
