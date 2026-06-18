"""
Create a Stripe Checkout Session for an org to subscribe.

The session carries ``client_reference_id = org_id`` (and the same id in both the
session and subscription metadata) so the webhook (``events.plan_from_event`` +
``service.apply_plan_update``) can link the resulting Stripe customer to the org
and flip its ``plan_*`` columns — both on the initial checkout and on later
``customer.subscription.updated`` events. ``stripe`` is imported lazily so the
core app stays importable without the SDK.
"""
from __future__ import annotations

from typing import Optional

from . import config


class CheckoutError(Exception):
    """Checkout could not be created (misconfig or Stripe API error)."""


def create_checkout_session(
    *,
    org_id: int,
    tier: str,
    success_url: str,
    cancel_url: str,
    customer_id: Optional[str] = None,
    customer_email: Optional[str] = None,
    price_id: Optional[str] = None,
) -> str:
    """Create a subscription Checkout Session and return its redirect URL."""
    if not config.stripe_secret_key():
        raise CheckoutError("STRIPE_SECRET_KEY is not configured")

    price = (price_id or "").strip() or config.price_for_tier(tier)
    if not price:
        raise CheckoutError(f"no Stripe price configured for tier '{tier}'")

    try:
        import stripe
    except ImportError as exc:  # pragma: no cover - environment issue
        raise CheckoutError(f"stripe SDK not installed: {exc}") from exc

    stripe.api_key = config.stripe_secret_key()
    metadata = {"org_id": str(org_id), "tier": tier}
    params: dict = dict(
        mode="subscription",
        line_items=[{"price": price, "quantity": 1}],
        client_reference_id=str(org_id),
        metadata=metadata,
        # Mirror onto the subscription so subscription.* webhooks carry org_id/tier.
        subscription_data={"metadata": metadata},
        success_url=success_url,
        cancel_url=cancel_url,
        allow_promotion_codes=True,
    )
    # Reuse the org's existing Stripe customer if it has one; else let Stripe
    # create one from the email (the webhook links it back via client_reference_id).
    if customer_id:
        params["customer"] = customer_id
    elif customer_email:
        params["customer_email"] = customer_email

    try:
        session = stripe.checkout.Session.create(**params)
    except Exception as exc:  # stripe.error.* and friends
        raise CheckoutError(f"stripe checkout failed: {exc}") from exc

    return session.url
