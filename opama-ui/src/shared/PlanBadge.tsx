/** ******************************************************************
 * Plan badge / upgrade entry (pool tenancy).
 *
 * Shown in the header only when hosted billing is configured (GET /billing/config)
 * AND the active org is below premium AND the caller is the org owner (only the
 * billing owner can subscribe). Clicking starts a Stripe Checkout for the active
 * org and redirects. Returns nothing on OSS/self-host or for already-paid orgs, so
 * it's invisible everywhere billing isn't in play.
 *
 * After Stripe redirects back with `?billing=success`, the plan flip happens
 * asynchronously via the webhook (~seconds), so we briefly poll /auth/orgs and
 * show a "Finalizing…" state until the tier upgrades.
 ******************************************************************* */

import { useEffect, useState } from "react";
import { Sparkles, Loader2 } from "lucide-react";
import { api } from "../lib/api";
import { getBillingConfig, startCheckout } from "../lib/billing";
import { getActiveOrgId } from "../lib/activeOrg";

const TIER_RANK: Record<string, number> = { core: 0, free: 1, premium: 2, enterprise: 3 };

type OrgSummary = { id: number; plan_tier: string; plan_status: string; role: string };

function isPaid(o: OrgSummary): boolean {
  return (TIER_RANK[o.plan_tier] ?? 0) >= TIER_RANK.premium && o.plan_status === "active";
}

function pickActive(list: OrgSummary[]): OrgSummary | null {
  const id = getActiveOrgId();
  return list.find((o) => o.id === id) ?? list[0] ?? null;
}

export default function PlanBadge() {
  const [enabled, setEnabled] = useState(false);
  const [org, setOrg] = useState<OrgSummary | null>(null);
  const [busy, setBusy] = useState(false);

  const justCheckedOut =
    new URLSearchParams(window.location.search).get("billing") === "success";
  const [finalizing, setFinalizing] = useState(justCheckedOut);

  useEffect(() => {
    let alive = true;
    getBillingConfig().then((c) => alive && setEnabled(c.enabled)).catch(() => {});
    api<OrgSummary[]>("/auth/orgs")
      .then((list) => alive && setOrg(pickActive(list)))
      .catch(() => {});
    return () => { alive = false; };
  }, []);

  // After returning from Checkout, poll until the webhook flips the plan.
  useEffect(() => {
    if (!finalizing) return;
    let alive = true;
    let tries = 0;
    const tick = async () => {
      tries += 1;
      try {
        const list = await api<OrgSummary[]>("/auth/orgs");
        const active = pickActive(list);
        if (!alive) return;
        if (active) setOrg(active);
        if ((active && isPaid(active)) || tries >= 6) {
          setFinalizing(false);
          return;
        }
      } catch { /* keep trying */ }
      if (alive) setTimeout(tick, 2500);
    };
    const t = setTimeout(tick, 1500);
    return () => { alive = false; clearTimeout(t); };
  }, [finalizing]);

  if (!enabled || !org) return null;
  if (org.role !== "owner") return null;        // only the billing owner subscribes
  if (isPaid(org) && !finalizing) return null;  // already paid — nothing to upsell

  if (finalizing) {
    return (
      <span className="h-8 flex items-center gap-1.5 px-2.5 rounded-lg text-sm font-medium text-amber-700 bg-amber-50">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span className="hidden sm:inline">Finalizing…</span>
      </span>
    );
  }

  const upgrade = async () => {
    setBusy(true);
    try {
      await startCheckout("premium");
    } catch (e) {
      setBusy(false);
      console.error("checkout failed", e);
    }
  };

  return (
    <button
      onClick={upgrade}
      disabled={busy}
      title="Upgrade to Premium"
      className="h-8 flex items-center gap-1.5 px-2.5 rounded-lg text-sm font-medium text-white bg-gradient-to-r from-amber-500 to-orange-500 hover:opacity-90 disabled:opacity-60 transition-opacity"
    >
      <Sparkles className="w-4 h-4 flex-shrink-0" />
      <span className="hidden sm:inline">{busy ? "Redirecting…" : "Upgrade"}</span>
    </button>
  );
}
