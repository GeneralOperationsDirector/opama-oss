"""
Normalize a verified Stripe event into a ``PlanUpdate`` — the desired end-state
for one Organization's entitlement columns. Pure functions, no I/O: unit-test
with a plain dict, no Stripe account or network.

The pool model has no provisioning, so an event maps to a row update, not a
lifecycle action. ``tier``/``modules`` are ``None`` for lapse events (cancel /
payment failure) — we change only ``status`` (and period) and deliberately keep
the tier the org *had*, matching the Organization model's contract that
``plan_status`` gates access without forgetting the tier.

Plan derivation precedence for active events (tier, modules):
  1. object ``metadata.tier`` / ``metadata.modules``  (set on the Checkout)
  2. a subscription line item whose price is in STRIPE_PRICE_PLANS
  3. BILLING_DEFAULT_TIER / BILLING_DEFAULT_MODULES   (so canned `stripe trigger`
                                                       events still grant a plan)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from . import config

# Stripe event type → ("active" plan refresh) or ("lapse" status-only) handling.
_ACTIVATE = {
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
}
_CANCEL = {"customer.subscription.deleted"}
_PAST_DUE = {"invoice.payment_failed"}


@dataclass
class PlanUpdate:
    """Desired entitlement state for the org this event concerns."""

    stripe_customer_id: Optional[str]
    org_id: Optional[int]            # from checkout client_reference_id / metadata
    status: str                      # active | trialing | past_due | canceled
    tier: Optional[str] = None       # None = leave the org's current tier unchanged
    modules: Optional[str] = None    # None = leave unchanged
    period_end: Optional[datetime] = None


def _org_id_from_object(obj: dict) -> Optional[int]:
    metadata = obj.get("metadata") or {}
    candidate = obj.get("client_reference_id") or metadata.get("org_id")
    if candidate in (None, ""):
        return None
    try:
        return int(candidate)
    except (TypeError, ValueError):
        return None


def _plan_from_object(obj: dict) -> tuple[str, str]:
    metadata = obj.get("metadata") or {}
    if metadata.get("tier"):
        return metadata["tier"], metadata.get("modules", "*") or "*"

    plans = config.price_plans()
    items = ((obj.get("items") or {}).get("data")) or []
    for item in items:
        price_id = (item.get("price") or {}).get("id")
        if price_id and price_id in plans:
            return plans[price_id]

    return config.default_tier(), config.default_modules()


def _period_end_from_object(obj: dict) -> Optional[datetime]:
    ts = obj.get("current_period_end")
    if ts:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc)
    return None


def plan_from_event(event: dict) -> Optional[PlanUpdate]:
    """Map a verified Stripe event to a ``PlanUpdate``, or ``None`` to ignore it."""
    event_type = event.get("type", "")
    obj = (event.get("data") or {}).get("object") or {}
    customer = obj.get("customer")
    org_id = _org_id_from_object(obj)

    if event_type in _ACTIVATE:
        tier, modules = _plan_from_object(obj)
        # A subscription object carries its own lifecycle status; a checkout
        # session does not, so treat completion as active.
        status = obj.get("status") if obj.get("object") == "subscription" else "active"
        period_end = _period_end_from_object(obj)
        if period_end is None:
            period_end = datetime.now(tz=timezone.utc) + timedelta(
                days=config.default_period_days()
            )
        return PlanUpdate(
            stripe_customer_id=customer,
            org_id=org_id,
            status=status or "active",
            tier=tier,
            modules=modules,
            period_end=period_end,
        )

    if event_type in _CANCEL:
        return PlanUpdate(
            stripe_customer_id=customer,
            org_id=org_id,
            status="canceled",
            period_end=_period_end_from_object(obj),
        )

    if event_type in _PAST_DUE:
        return PlanUpdate(
            stripe_customer_id=customer,
            org_id=org_id,
            status="past_due",
        )

    return None
