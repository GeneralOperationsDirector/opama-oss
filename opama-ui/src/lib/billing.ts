/** ******************************************************************
 * Hosted billing (pool tenancy).
 *
 * Thin client for the pool billing endpoints. `GET /billing/config` reports
 * whether checkout is configured at all (so the UI hides upgrade affordances on
 * an OSS/self-host instance). `POST /billing/checkout` creates a Stripe Checkout
 * Session for the active org and returns its redirect URL — the session carries
 * `client_reference_id=<org_id>`, so the webhook links the resulting customer to
 * the org and flips its plan. We just redirect the browser to the URL.
 ******************************************************************* */

import { api } from "./api";

export type BillingConfig = { enabled: boolean };

export async function getBillingConfig(): Promise<BillingConfig> {
  return api<BillingConfig>("/billing/config");
}

/** Start a subscription checkout for the active org and redirect to Stripe. */
export async function startCheckout(tier = "premium"): Promise<void> {
  const { url } = await api<{ url: string }>("/billing/checkout", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tier }),
  });
  window.location.href = url;
}
