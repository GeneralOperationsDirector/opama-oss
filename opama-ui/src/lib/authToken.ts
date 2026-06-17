/** ******************************************************************
 * Provider-aware bearer token resolution.
 *
 * opama supports two auth providers (selected server-side via AUTH_PROVIDER):
 * - "firebase": tokens are Firebase ID tokens (auth.currentUser.getIdToken())
 * - "local":    tokens are long-lived opama-issued JWTs, stored client-side
 *
 * `getAuthToken()` is the single place that knows how to fetch "the current
 * bearer token" regardless of which provider is active — used by both
 * lib/api.ts's getAuthHeaders() and the raw-fetch multipart upload call sites
 * (GradeResultCard, AssetForm) that previously reached into Firebase directly.
 ******************************************************************* */

import { auth } from "./firebase";
import { orgHeader } from "./activeOrg";

const API_BASE: string =
  (import.meta as any).env?.VITE_API_BASE ?? "http://localhost:8008";

const LOCAL_TOKEN_KEY = "opama_local_token";

export type AuthProviderName = "local" | "firebase";

export function getStoredLocalToken(): string | null {
  try {
    return localStorage.getItem(LOCAL_TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setStoredLocalToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(LOCAL_TOKEN_KEY, token);
    else localStorage.removeItem(LOCAL_TOKEN_KEY);
  } catch {
    /* localStorage unavailable (e.g. private browsing) — token won't persist */
  }
}

/** GET /auth/config is fetched once and cached — the active provider never
 * changes at runtime (it's a server deployment setting). */
let _providerPromise: Promise<AuthProviderName> | null = null;

export function getAuthProviderName(): Promise<AuthProviderName> {
  if (!_providerPromise) {
    _providerPromise = fetch(`${API_BASE}/auth/config`)
      .then((r) => r.json())
      .then((d) => (d?.provider === "firebase" ? "firebase" : "local"))
      .catch(() => "local" as const);
  }
  return _providerPromise;
}

/** Resolve the current bearer token for API requests, or null if signed out. */
export async function getAuthToken(): Promise<string | null> {
  const provider = await getAuthProviderName();

  if (provider === "firebase") {
    await auth.authStateReady();
    const user = auth.currentUser;
    if (!user) return null;
    try {
      return await user.getIdToken();
    } catch (err) {
      console.error("Failed to get Firebase auth token:", err);
      return null;
    }
  }

  return getStoredLocalToken();
}

/**
 * Headers for an authenticated API request: the bearer token plus the active-org
 * header (`X-Org-Id`). The single place both lib/api.ts and the raw-fetch
 * multipart upload call sites build request headers, so org scoping is uniform.
 */
export async function getRequestHeaders(): Promise<Record<string, string>> {
  const token = await getAuthToken();
  return {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...orgHeader(),
  };
}
