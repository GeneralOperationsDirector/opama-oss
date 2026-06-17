/** ******************************************************************
 * Active-organization state (pool tenancy).
 *
 * Every request resolves to one organization — the unit that owns collection
 * data (see the backend pool_vs_silo design). A solo collector is an org-of-one;
 * a store's staff share the store's org. The user picks an active org in the
 * switcher; we persist its id and send it as the `X-Org-Id` header on every API
 * call (resolution is per-request server-side — there is no "current org" to
 * POST). When unset, the server falls back to the caller's personal org.
 ******************************************************************* */

const ACTIVE_ORG_KEY = "opama_active_org_id";
const CHANGE_EVENT = "opama:active-org-changed";

export function getActiveOrgId(): number | null {
  try {
    const raw = localStorage.getItem(ACTIVE_ORG_KEY);
    if (!raw) return null;
    const n = Number(raw);
    return Number.isFinite(n) ? n : null;
  } catch {
    return null;
  }
}

/**
 * Persist the active org id. By default emits a window event so listeners (the
 * switcher / app shell) can react; pass `emit: false` to seed the default from
 * /auth/me without triggering a reload.
 */
export function setActiveOrgId(id: number | null, emit = true): void {
  try {
    if (id == null) localStorage.removeItem(ACTIVE_ORG_KEY);
    else localStorage.setItem(ACTIVE_ORG_KEY, String(id));
  } catch {
    /* localStorage unavailable (private browsing) — won't persist */
  }
  if (emit) {
    try {
      window.dispatchEvent(new CustomEvent(CHANGE_EVENT, { detail: id }));
    } catch {
      /* SSR / no window */
    }
  }
}

/** The `X-Org-Id` header object (empty when no active org is set). */
export function orgHeader(): Record<string, string> {
  const id = getActiveOrgId();
  return id != null ? { "X-Org-Id": String(id) } : {};
}

/** Subscribe to active-org changes; returns an unsubscribe fn. */
export function onActiveOrgChange(cb: (id: number | null) => void): () => void {
  const handler = (e: Event) => cb((e as CustomEvent).detail ?? null);
  window.addEventListener(CHANGE_EVENT, handler);
  return () => window.removeEventListener(CHANGE_EVENT, handler);
}
