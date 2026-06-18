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
