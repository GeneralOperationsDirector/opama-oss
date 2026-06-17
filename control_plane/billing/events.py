"""
Normalize a Stripe event into a PlanIntent — the control plane's own
provider-agnostic description of "what should happen to which tenant".

This is the one place that knows Stripe's object shapes, so the webhook route
and the tenant service layer never do. Pure functions, no I/O — unit-testable
with a plain dict, no Stripe account or network.

Plan derivation precedence (tier, modules):
  1. event object `metadata.tier` / `metadata.modules`   (easy to set on a Checkout)
  2. a subscription line item whose price is in settings.price_plans
  3. settings.default_tier / default_modules               (lets `stripe trigger`
                                                             canned events provision)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from control_plane.config import settings

# Stripe event type → the lifecycle action it triggers.
EVENT_ACTIONS: dict[str, str] = {
    "checkout.session.completed": "provision",
    "customer.subscription.created": "provision",
    "customer.subscription.updated": "relicense",
    "customer.subscription.deleted": "deprovision",
    "invoice.payment_failed": "deprovision",
}


@dataclass
class PlanIntent:
    action: str                       # provision | relicense | deprovision
    stripe_customer_id: str | None
    stripe_subscription_id: str | None
    email: str | None
    tier: str
    modules: str
    period_end: datetime
    destroy: bool = False

    @property
    def slug(self) -> str:
        """Deterministic, container/DB/URL-safe identifier. Derived from the
        Stripe customer id (stable across a customer's events), falling back to
        email then a constant."""
        return _slugify(self.stripe_customer_id or self.email or "tenant")


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower().strip()).strip("-")
    return slug or "tenant"


def _plan_from_object(obj: dict) -> tuple[str, str]:
    metadata = obj.get("metadata") or {}
    if metadata.get("tier"):
        return metadata["tier"], metadata.get("modules", "*")

    items = ((obj.get("items") or {}).get("data")) or []
    for item in items:
        price_id = (item.get("price") or {}).get("id")
        if price_id and price_id in settings.price_plans:
            return settings.price_plans[price_id]

    return settings.default_tier, settings.default_modules


def _period_end_from_object(obj: dict) -> datetime:
    ts = obj.get("current_period_end")
    if ts:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc)
    return datetime.now(tz=timezone.utc) + timedelta(days=settings.default_period_days)


def _email_from_object(obj: dict) -> str | None:
    details = obj.get("customer_details") or {}
    return details.get("email") or obj.get("customer_email") or obj.get("email")


def plan_from_event(event: dict) -> PlanIntent | None:
    """Map a verified Stripe event to a PlanIntent, or None to ignore it."""
    event_type = event.get("type", "")
    action = EVENT_ACTIONS.get(event_type)
    if action is None:
        return None

    obj = (event.get("data") or {}).get("object") or {}

    # A subscription object's own id is the subscription id; a checkout session
    # references it via `subscription`.
    if obj.get("object") == "subscription":
        subscription_id = obj.get("id")
    else:
        subscription_id = obj.get("subscription")

    tier, modules = _plan_from_object(obj)

    return PlanIntent(
        action=action,
        stripe_customer_id=obj.get("customer"),
        stripe_subscription_id=subscription_id,
        email=_email_from_object(obj),
        tier=tier,
        modules=modules,
        period_end=_period_end_from_object(obj),
        destroy=(action == "deprovision" and settings.destroy_on_cancel),
    )
