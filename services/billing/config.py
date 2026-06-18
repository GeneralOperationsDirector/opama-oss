"""
Billing configuration, read from the environment.

Kept tiny and self-contained (no dependency on the control plane's settings) so
the pool webhook ships in the core/OSS app. Read lazily via functions rather
than module-level constants so tests can monkeypatch ``os.environ`` per case.
"""
from __future__ import annotations

import os


def stripe_webhook_secret() -> str:
    """The ``whsec_...`` secret used to verify the Stripe-Signature header."""
    return os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()


def stripe_secret_key() -> str:
    """The ``sk_...`` secret key used to create Checkout Sessions."""
    return os.getenv("STRIPE_SECRET_KEY", "").strip()


def price_for_tier(tier: str) -> str:
    """Resolve a Stripe price id to sell for ``tier``.

    Inverts STRIPE_PRICE_PLANS (price → (tier, modules)); the first price mapped
    to the requested tier wins. Empty if none configured.
    """
    for price_id, (plan_tier, _modules) in price_plans().items():
        if plan_tier == tier:
            return price_id
    return ""


def checkout_enabled() -> bool:
    """True when a Checkout can actually be created (secret key + a sellable price)."""
    return bool(stripe_secret_key() and price_plans())


def _origin_join(origin: str, path: str) -> str:
    return f"{origin.rstrip('/')}{path}"


def checkout_success_url(origin: str) -> str:
    """Where Stripe returns after a completed checkout. Configurable; defaults to
    the caller's app origin so it works without extra setup."""
    return os.getenv("BILLING_SUCCESS_URL", "").strip() or _origin_join(origin, "/?billing=success")


def checkout_cancel_url(origin: str) -> str:
    return os.getenv("BILLING_CANCEL_URL", "").strip() or _origin_join(origin, "/?billing=cancel")


def price_plans() -> dict[str, tuple[str, str]]:
    """Map a Stripe price id → (tier, modules).

    Parsed from ``STRIPE_PRICE_PLANS`` as a **semicolon**-separated list of
    ``price_id:tier:modules`` triples (modules optional, defaults to ``*``)::

        STRIPE_PRICE_PLANS="price_abc:premium:*;price_def:enterprise:portfolio,grading"

    Entries are split on ``;`` (not ``,``) precisely so ``modules`` can itself be
    a comma-separated list; each entry is then split on the first two colons.
    """
    raw = os.getenv("STRIPE_PRICE_PLANS", "").strip()
    plans: dict[str, tuple[str, str]] = {}
    if not raw:
        return plans
    for entry in raw.split(";"):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        parts = entry.split(":")
        price_id = parts[0].strip()
        tier = parts[1].strip() if len(parts) > 1 else ""
        modules = ":".join(parts[2:]).strip() if len(parts) > 2 else "*"
        if price_id and tier:
            plans[price_id] = (tier, modules or "*")
    return plans


def default_tier() -> str:
    """Tier applied when an event has no metadata.tier and no known price.
    Lets canned ``stripe trigger`` events still grant something in testing."""
    return os.getenv("BILLING_DEFAULT_TIER", "premium").strip()


def default_modules() -> str:
    return os.getenv("BILLING_DEFAULT_MODULES", "*").strip() or "*"


def default_period_days() -> int:
    try:
        return int(os.getenv("BILLING_DEFAULT_PERIOD_DAYS", "30"))
    except ValueError:
        return 30
