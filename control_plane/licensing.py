"""
License minting — the control plane's private-key side of the license system.

This is the canonical signer. Validation lives in opama core (app/license.py,
embedded *public* key); minting lives here in the control plane with the *private*
key, which never ships in a tenant image. The claim shape below must stay in
lockstep with app.license.decode_license (iss/sub/exp/iat required, iss=="opama").

The private key is loaded from OPAMA_LICENSE_SIGNING_KEY (path), default
./license_signing_key.pem — the same key scripts/generate_license_key.py uses, so
the two mint interchangeable keys. Create a keypair with:
    openssl genrsa -out license_signing_key.pem 2048
(the matching public key goes in app/license.py).
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import jwt

_KEY_PATH = os.environ.get("OPAMA_LICENSE_SIGNING_KEY", "license_signing_key.pem")

# Mirrors the tier hierarchy in app/license.py (TIER_RANK). Kept here so the
# control plane stays a leaf that doesn't import opama core.
VALID_TIERS = {"core", "free", "premium", "enterprise"}


def load_private_key() -> str | None:
    """Read the RSA private signing key, or None if it isn't present.

    Returning None (rather than raising) lets callers degrade gracefully — e.g.
    the control plane can boot a tenant in dev mode when no key is configured,
    and tests can import this module without a key on disk."""
    try:
        with open(_KEY_PATH) as fh:
            return fh.read()
    except FileNotFoundError:
        return None


def has_signing_key() -> bool:
    return load_private_key() is not None


def _normalize_modules(modules: str | list[str]) -> str | list[str]:
    """Accept "*", a comma string, or a list → the claim shape app.license expects."""
    if isinstance(modules, list):
        return modules
    if modules.strip() == "*":
        return "*"
    return [m.strip() for m in modules.split(",") if m.strip()]


def sign_license(
    customer: str,
    tier: str,
    modules: str | list[str],
    expires_at: datetime,
    *,
    jti: str | None = None,
) -> str:
    """Mint an RS256 license JWT.

    `expires_at` is an absolute datetime (the control plane sets it to the Stripe
    subscription's current_period_end so a lapse self-degrades the instance on its
    next restart) — unlike scripts/generate_license_key.py's days-from-now param.
    """
    key = load_private_key()
    if key is None:
        raise RuntimeError(
            f"license signing key not found at {_KEY_PATH!r}. "
            "Set OPAMA_LICENSE_SIGNING_KEY or place license_signing_key.pem in the CWD."
        )
    now = datetime.now(tz=timezone.utc)
    payload = {
        "iss": "opama",
        "sub": customer,
        "customer": customer,
        "tier": tier,
        "modules": _normalize_modules(modules),
        "iat": now,
        "exp": expires_at,
        "jti": jti or str(uuid.uuid4()),
    }
    return jwt.encode(payload, key, algorithm="RS256")


def mint_for_tenant(tenant, subscription) -> str:
    """Mint the license a tenant should boot with, from its Subscription.

    Typed loosely to avoid importing the models here (keeps this module a leaf —
    control_plane.cli / the M3 webhook pass in the rows). `current_period_end`
    must be set; the caller computes it (Stripe provides it; the CLI derives it
    from --days).
    """
    if subscription.current_period_end is None:
        raise ValueError("subscription.current_period_end is required to mint a license")
    return sign_license(
        customer=tenant.customer_email or tenant.slug,
        tier=subscription.tier,
        modules=subscription.modules,
        expires_at=subscription.current_period_end,
    )
