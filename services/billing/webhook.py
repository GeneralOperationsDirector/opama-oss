"""
Stripe webhook signature verification for the pool billing route.

Mirrors the control plane's approach: ``stripe.Webhook.construct_event`` both
verifies the ``Stripe-Signature`` header against ``STRIPE_WEBHOOK_SECRET`` and
parses the JSON; either failure raises ``WebhookError`` (→ 400 at the route).
``stripe`` is imported lazily so the core app stays importable without the SDK
(an OSS self-host that never bills). We re-parse the already-authenticated
payload into a plain dict because the ``stripe.Event`` StripeObject's ``.get()``
is not dict-like, and ``events.plan_from_event`` treats events as plain dicts.
"""
from __future__ import annotations

import json

from . import config


class WebhookError(Exception):
    """Signature verification or payload parsing failed."""


def construct_event(payload: bytes, sig_header: str) -> dict:
    """Verify a Stripe webhook and return the event as a plain dict."""
    secret = config.stripe_webhook_secret()
    if not secret:
        raise WebhookError("STRIPE_WEBHOOK_SECRET is not configured")

    try:
        import stripe
    except ImportError as exc:  # pragma: no cover - environment issue
        raise WebhookError(f"stripe SDK not installed: {exc}") from exc

    try:
        stripe.Webhook.construct_event(payload, sig_header, secret)
    except ValueError as exc:  # malformed JSON
        raise WebhookError(f"invalid payload: {exc}") from exc
    except stripe.error.SignatureVerificationError as exc:  # bad/forged signature
        raise WebhookError(f"signature verification failed: {exc}") from exc

    return json.loads(payload)
