/** ******************************************************************
 * Minimal API client for the Pokémon TCG app
 * - Small, typed wrappers around fetch()
 * - Sensible defaults (timeout, JSON parse, errors with body text)
 * - Domain helpers used by tabs/components
 * - Firebase Authentication integration
 *
 * NOTE: We preserve your original `api<T>()` so existing imports keep working.
 ******************************************************************* */

import { getAuthToken } from './authToken';

export const API_BASE: string =
  (import.meta as any).env?.VITE_API_BASE ?? "http://localhost:8008";

/** Abortable timeout for fetch calls (ms). Tweak if your server is chatty. */
const DEFAULT_TIMEOUT = 25_000;

/** Lightweight sleep used by retry. */
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Build the Authorization header for the active auth provider (Firebase ID
 * token or locally-stored opama token — see lib/authToken.ts). */
async function getAuthHeaders(): Promise<HeadersInit> {
  const token = await getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Build URL with optional query params (auto-encodes and drops null/undefined). */
function makeURL(path: string, query?: Record<string, any>): string {
  if (!query || Object.keys(query).length === 0) return `${API_BASE}${path}`;
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === "") continue;
    qs.set(k, String(v));
  }
  const q = qs.toString();
  return `${API_BASE}${path}${q ? `?${q}` : ""}`;
}

/** Core fetch wrapper (JSON in/out). Kept compatible with your prior api<T>(). */
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const authHeaders = await getAuthHeaders();
  const headers = { ...init?.headers, ...authHeaders };

  const r = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!r.ok) throw new Error(await safeText(r));
  // 204/empty
  if (r.status === 204) return undefined as unknown as T;
  return (await r.json()) as T;
}

/** Newer helper: GET with timeout + tiny retry (good for flakey networks). */
async function getJSON<T>(
  path: string,
  opts?: { query?: Record<string, any>; timeout?: number; retries?: number }
): Promise<T> {
  const url = makeURL(path, opts?.query);
  const retries = Math.max(0, opts?.retries ?? 0);
  const timeout = opts?.timeout ?? DEFAULT_TIMEOUT;
  const authHeaders = await getAuthHeaders();

  let lastErr: unknown;
  for (let attempt = 0; attempt <= retries; attempt++) {
    const ac = new AbortController();
    const tid = setTimeout(() => ac.abort(), timeout);
    try {
      const r = await fetch(url, { signal: ac.signal, headers: authHeaders });
      clearTimeout(tid);
      if (!r.ok) throw new Error(await safeText(r));
      if (r.status === 204) return undefined as unknown as T;
      return (await r.json()) as T;
    } catch (e) {
      clearTimeout(tid);
      lastErr = e;
      if (attempt < retries) {
        await sleep(200 * (attempt + 1));
        continue;
      }
      throw e;
    }
  }
  // TypeScript happiness
  throw lastErr instanceof Error ? lastErr : new Error(String(lastErr));
}

async function jsonBody<T>(
  path: string,
  body: unknown,
  method: "POST" | "PATCH" | "PUT" | "DELETE" = "POST",
  timeout = DEFAULT_TIMEOUT
): Promise<T> {
  const authHeaders = await getAuthHeaders();
  const ac = new AbortController();
  const tid = setTimeout(() => ac.abort(), timeout);
  const r = await fetch(`${API_BASE}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders,
    },
    body: body != null ? JSON.stringify(body) : undefined,
    signal: ac.signal,
  });
  clearTimeout(tid);
  if (!r.ok) throw new Error(await safeText(r));
  if (r.status === 204) return undefined as unknown as T;
  return (await r.json()) as T;
}

async function safeText(r: Response) {
  try {
    return await r.text();
  } catch {
    return `${r.status} ${r.statusText}`;
  }
}

// ---------------------------------------------------------------------------
// Domain helpers (used across tabs)
// ---------------------------------------------------------------------------

import type {
  Deck,
  DeckWithCards,
  DeckCardHydrated,
  PatchDeckCardPayload,
  Rec, // from Suggestion types if present
  AiSuggestIn,
  AiSuggestOut,
} from "../types";

// -------------------- Decks --------------------

/** Fetch decks for a user (used by app shell + Decks tab). */
export async function fetchDecksForUser(userId: number) {
  return getJSON<Deck[]>(`/decks`, { query: { user_id: userId } });
}

/** Create a deck. Server defaults: format="Standard" if omitted (your router). */
export async function createDeck(body: {
  user_id: number;
  name: string;
  format?: string;
}) {
  return jsonBody<{ id: number }>(`/decks`, body, "POST");
}

/** Get a deck with hydrated cards. */
export function getDeck(deckId: number) {
  return getJSON<DeckWithCards>(`/decks/${deckId}`);
}

/** Rename/update deck properties. */
export function patchDeck(deckId: number, body: Partial<Deck>) {
  return jsonBody<Deck>(`/decks/${deckId}`, body, "PATCH");
}

// compat for older code: rename a deck by name
export function renameDeck(deckId: number, name: string) {
  return patchDeck(deckId, { name });
}


/** Delete a deck. */
export function deleteDeck(deckId: number) {
  return jsonBody<void>(`/decks/${deckId}`, null, "DELETE");
}

/** Add a card to a deck (creates or increments server-side). */
export function addDeckCard(deckId: number, card_id: string, quantity = 1) {
  return jsonBody<{ id: number }>(`/decks/${deckId}/cards`, { card_id, quantity }, "POST");
}

/** Update a deck card line (qty/role/etc.). */
export function patchDeckCard(
  deckId: number,
  deckCardId: number,
  payload: PatchDeckCardPayload
) {
  return jsonBody<DeckCardHydrated>(
    `/decks/${deckId}/cards/${deckCardId}`,
    payload,
    "PATCH"
  );
}

/** Remove a deck card line. */
export function deleteDeckCard(deckId: number, deckCardId: number) {
  return jsonBody<void>(`/decks/${deckId}/cards/${deckCardId}`, null, "DELETE");
}

// compat alias for older import names
export { deleteDeckCard as removeDeckCard };


// -------------------- Inventory --------------------

/** Get inventory for a user. (Your backend may support `?user_id=` or `/inventory/{user}`.) */
export function getInventory(userId: number) {
  return getJSON<any[]>(`/inventory`, { query: { user_id: userId } });
}

/** Add/adjust inventory items. */
export function addInventoryItem(user_id: number, card_id: string, quantity = 1) {
  return jsonBody(`/inventory`, { user_id, card_id, quantity }, "POST");
}

export function patchInventoryItem(user_id: number, card_id: string, quantity: number) {
  return jsonBody(`/inventory`, { user_id, card_id, quantity }, "PATCH");
}

export function removeInventoryItem(user_id: number, card_id: string) {
  return jsonBody(`/inventory`, { user_id, card_id }, "DELETE");
}

// -------------------- Wishlist --------------------

export function getWishlist(userId: number) {
  return getJSON<{ wishlist: any; card: any }[]>(`/user/${userId}/wishlist`);
}

export function addToWishlist(userId: number, cardId: string) {
  return jsonBody<{ ok: boolean; id: number }>(
    `/user/${userId}/wishlist/${encodeURIComponent(cardId)}`,
    null,
    "POST"
  );
}

export function removeFromWishlist(userId: number, cardId: string) {
  return jsonBody<{ ok: boolean }>(
    `/user/${userId}/wishlist/${encodeURIComponent(cardId)}`,
    null,
    "DELETE"
  );
}

// -------------------- Trade --------------------

export function getTradeList(userId: number) {
  return getJSON<{ trade: any; card: any }[]>(`/user/${userId}/trade`);
}

export function upsertTradeItem(
  userId: number,
  cardId: string,
  quantity = 1,
  condition?: string
) {
  const qs = new URLSearchParams({ quantity: String(quantity) });
  if (condition) qs.set("condition", condition);
  return jsonBody<{ ok: boolean; id: number; quantity: number }>(
    `/user/${userId}/trade/${encodeURIComponent(cardId)}?${qs.toString()}`,
    null,
    "POST"
  );
}

export function removeTradeItem(userId: number, cardId: string) {
  return jsonBody<{ ok: boolean }>(
    `/user/${userId}/trade/${encodeURIComponent(cardId)}`,
    null,
    "DELETE"
  );
}

// -------------------- Cards & Sets --------------------

export function listSets() {
  return getJSON<any[]>(`/cards/sets`);
}

export function searchCards(params: {
  q?: string;
  set_id?: string;
  limit?: number;
  offset?: number;
}) {
  return getJSON<{ total: number; items: any[] }>(`/cards/search`, { query: params });
}

export function getCardById(cardId: string) {
  return getJSON<any>(`/cards/${encodeURIComponent(cardId)}`);
}

// -------------------- Suggestions / AI --------------------

/** Heuristic suggestions (supports pagination + ownership filters). */
export function getHeuristicSuggestions(params: {
  deck_id: number;
  user_id?: number;
  limit?: number;
  offset?: number;
  owned_only?: boolean;
  acquire_only?: boolean;
  cache_seconds?: number;
}) {
  const { deck_id, ...rest } = params;
  return getJSON<{ recommendations: Rec[]; note?: string }>(`/suggest/${deck_id}`, {
    query: rest,
  });
}

/** LLM suggestions (strict JSON on the server). */
export function postAiSuggest(body: AiSuggestIn) {
  return jsonBody<AiSuggestOut>(`/suggest/ai`, body, "POST");
}

/** Deck chat (compact deck context is injected server-side). */
export function postDeckChat(payload: {
  deck_id: number;
  user_id?: number | string;
  messages: { role: "system" | "user" | "assistant"; content: string }[];
  model?: string;
  temperature?: number;
}) {
  return jsonBody<{ reply: string; model: string; usage?: Record<string, any> }>(
    `/suggest/chat`,
    payload,
    "POST"
  );
}

// -------------------- eBay --------------------

export function ebaySearch(params: {
  q: string;
  limit?: number;
  offset?: number;
  condition?: string;
}) {
  return getJSON<{ total: number; items: any[] }>(`/api/ebay/search`, { query: params });
}

// -------------------- Misc utils you might like --------------------

/** Convenience: POST JSON */
export const postJSON = <T>(path: string, body: unknown) => jsonBody<T>(path, body, "POST");

/** Convenience: PATCH JSON */
export const patchJSON = <T>(path: string, body: unknown) => jsonBody<T>(path, body, "PATCH");

/** Convenience: DELETE JSON (with body) */
export const delJSON = <T>(path: string, body?: unknown) => jsonBody<T>(path, body, "DELETE");
