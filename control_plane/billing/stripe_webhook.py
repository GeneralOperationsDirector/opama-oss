"""
Stripe webhook signature verification.

Wraps stripe.Webhook.construct_event so the rest of the control plane never
touches the raw HMAC. construct_event both verifies the `Stripe-Signature`
header against STRIPE_WEBHOOK_SECRET *and* parses the JSON — a request that
fails either step raises WebhookError, which the route turns into a 400.

stripe is imported lazily so the rest of control_plane (CLI, provisioner) stays
importable without the SDK installed.

We verify with stripe.Webhook.construct_event but return a *plain dict* (the raw
payload re-parsed) rather than the `stripe.Event` object it hands back: the Event
is a StripeObject whose `.get()` doesn't behave like a dict's, and the rest of the
control plane (events.plan_from_event) treats events as plain dicts. The payload
has already been authenticated by the time we parse it, so json.loads is safe.
"""
from __future__ import annotations

import json

from control_plane.config import settings


class WebhookError(Exception):
    """Signature verification or payload parsing failed."""


def construct_event(payload: bytes, sig_header: str) -> dict:
    """Verify + parse a Stripe webhook. Returns the Event (dict-like)."""
    if not settings.stripe_webhook_secret:
        raise WebhookError("STRIPE_WEBHOOK_SECRET is not configured")

    try:
        import stripe
    except ImportError as exc:  # pragma: no cover - environment issue
        raise WebhookError(f"stripe SDK not installed: {exc}") from exc

    try:
        # Verifies the HMAC signature (and parses); we discard its StripeObject
        # return and re-parse the now-authenticated payload into a plain dict.
        stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except ValueError as exc:                       # malformed JSON
        raise WebhookError(f"invalid payload: {exc}") from exc
    except stripe.error.SignatureVerificationError as exc:  # bad/forged signature
        raise WebhookError(f"signature verification failed: {exc}") from exc

    return json.loads(payload)
