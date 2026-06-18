"""
Per-request entitlement enforcement for the shared-DB "pool" tenancy model.

In the pool / SaaS deployment a single app fleet serves *every* tier at once,
so premium access can't be gated only at plugin-load time the way the silo /
OSS self-host path does (that decision is per-process, baked in at boot from
``OPAMA_LICENSE_KEY``). Instead each premium endpoint depends on
``require_tier(...)``, which reads the active Organization's ``plan_*`` columns
— flipped by the SaaS Stripe webhook — and rejects callers whose plan doesn't
cover the feature. No restart, no per-tenant key (see the pool_vs_silo memory).

Two modes, selected by the ``ENTITLEMENT_MODE`` env var:

  - ``license`` (default): boot-time license gating governs access (the OSS /
    self-host / silo path). ``require_tier`` is a **pass-through** here, so a
    self-hosted instance — where every org defaults to ``plan_tier="free"`` —
    behaves exactly as before. This is what keeps adding the dependency a
    no-op for existing deployments.
  - ``org``: per-request enforcement from ``Organization.plan_*`` (the SaaS
    pool path).

A shortfall raises **402 Payment Required** with a structured payload so the
frontend can drive an upgrade flow off a single status code.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status

from app.license import TIER_RANK
from services.shared.models import Organization

from .org_context import OrgContext, get_current_org

ENTITLEMENT_MODE_ENV = "ENTITLEMENT_MODE"

# Stripe subscription statuses that still grant access. A lapse (past_due,
# canceled, unpaid, incomplete, ...) gates without forgetting which tier they
# were on (plan_tier is left untouched).
_ACTIVE_STATUSES = frozenset({"active", "trialing"})


def entitlement_mode() -> str:
    """Current enforcement mode (``license`` default, or ``org`` for the pool)."""
    return os.getenv(ENTITLEMENT_MODE_ENV, "license").strip().lower()


def _module_allowed(plan_modules: str, module: str) -> bool:
    """True if ``module`` is covered by an org's ``plan_modules`` allow-list.

    ``"*"`` (or empty) means "every module in the tier" — the tier check has
    already run by the time we get here. Otherwise ``plan_modules`` is a
    comma-separated allow-list of module ids.
    """
    raw = (plan_modules or "").strip()
    if raw in ("", "*"):
        return True
    allowed = {m.strip() for m in raw.split(",") if m.strip()}
    return module in allowed


def org_entitlement_error(
    org: Organization,
    minimum_tier: str,
    module: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Optional[str]:
    """Pure check: return a human-readable reason if ``org`` is NOT entitled to
    ``minimum_tier`` (and optionally ``module``), else ``None``.

    Order: subscription status → period expiry (safety net for a missed
    webhook) → tier rank → module allow-list. Unknown tiers fail closed
    (rank 0 for the org, rank 99 for the requirement).
    """
    status_val = (org.plan_status or "").lower()
    if status_val not in _ACTIVE_STATUSES:
        return f"subscription is {status_val or 'inactive'}"

    end = org.current_period_end
    if end is not None:
        # DB datetimes are naive UTC; normalise before comparing.
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        if end < (now or datetime.now(timezone.utc)):
            return "subscription period has ended"

    if TIER_RANK.get(org.plan_tier, 0) < TIER_RANK.get(minimum_tier, 99):
        return f"requires the '{minimum_tier}' plan"

    if module and not _module_allowed(org.plan_modules, module):
        return f"module '{module}' is not included in your plan"

    return None


def assert_entitled(
    org: Organization,
    minimum_tier: str,
    module: Optional[str] = None,
) -> None:
    """Raise 402 if, in ``org`` enforcement mode, ``org`` lacks the entitlement.

    A no-op in the default ``license`` mode (boot-time gating already decided
    what is mounted), and the single choke point shared by the HTTP dependency
    and any non-HTTP caller (MCP tools) that already holds an Organization.
    """
    if entitlement_mode() != "org":
        return
    reason = org_entitlement_error(org, minimum_tier, module=module)
    if reason:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "upgrade_required",
                "reason": reason,
                "required_tier": minimum_tier,
                "current_tier": org.plan_tier,
                "module": module,
            },
        )


def require_tier(minimum_tier: str, module: Optional[str] = None):
    """Dependency factory: gate an endpoint behind a plan tier (+ optional module).

    Returns the active ``OrgContext`` (so it drops in for ``get_current_org``):

        require_portfolio = require_tier("premium", module="portfolio")

        @router.get("/value")
        def value(ctx: OrgContext = Depends(require_portfolio)):
            ...

    Build the dependency once at module load (as above) rather than calling
    ``require_tier(...)`` inline in every decorator.
    """

    async def _dep(ctx: OrgContext = Depends(get_current_org)) -> OrgContext:
        assert_entitled(ctx.org, minimum_tier, module=module)
        return ctx

    return _dep
