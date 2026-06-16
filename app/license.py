"""
License validation for opama.

License keys are RS256-signed JWTs. The embedded public key validates
them offline without any network call.

Tier hierarchy: core < free < premium < enterprise

Key generation: scripts/generate_license_key.py
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

try:
    import jwt
    from jwt.exceptions import InvalidTokenError as _JWTError
    _HAS_JWT = True
except ImportError:
    _HAS_JWT = False

# RSA-2048 public key (generated 2026-06-05, paired with generate_license_key.py)
_PUBLIC_KEY = """\
-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA3VqzJbWjsCt6MTpos0RH
JjzX5AI5kgUv7eT8BXdEzBC2GwxLZorCxj+p+E0uQVfn9wpsC+iU+DoqKJl1Whq/
C1lhnBm6htvQxS7bj6mzcGMHpSUEcpgfD5Vtpujhefrx9nYKPOXrnclqWgAucAUc
cx8LvpBufU69fYELVHL8v3GR0KIcyIXidHimmsp91ohtE0A5UR2wYPruYmJ8tTQ0
fjljTDUop1H7HD1d4NFECp+roO98/28NkNIsLUu6/+sNucQBdueauJtUsNb+npq1
bEGP79rKTN3bWLqFoMwUu52PSEc7smafPvXMDRrF3UlegSXc3IuFuO+ruf3SFHQq
2QIDAQAB
-----END PUBLIC KEY-----"""

TIER_RANK: dict[str, int] = {"core": 0, "free": 1, "premium": 2, "enterprise": 3}


@dataclass
class LicenseInfo:
    valid: bool
    tier: str = "core"
    # "*" means all modules; a list restricts to specific plugin IDs
    modules: list[str] | str = field(default_factory=list)
    customer: str = ""
    expires_at: datetime | None = None
    message: str = ""

    def covers_tier(self, plugin_tier: str) -> bool:
        """Return True if this license covers a plugin of the given tier."""
        if not self.valid and self.modules != "*":
            return False
        if self.modules == "*":
            return True
        return TIER_RANK.get(plugin_tier, 99) <= TIER_RANK.get(self.tier, 0)

    def allows_plugin(self, plugin_id: str, plugin_tier: str) -> bool:
        """Return True if this license enables a specific plugin."""
        if self.modules == "*":
            return True
        if isinstance(self.modules, list):
            # Explicit list: core plugins always load; others must be listed explicitly
            if plugin_tier == "core":
                return True
            return plugin_id in self.modules
        # Tier-based (modules not set / empty)
        return self.covers_tier(plugin_tier)


def decode_license(raw: str) -> LicenseInfo:
    """Decode and validate an opama RS256 license JWT."""
    raw = raw.strip()
    if not raw:
        return LicenseInfo(valid=False, message="empty key")

    if not _HAS_JWT:
        return LicenseInfo(valid=False, message="PyJWT not installed")

    try:
        payload = jwt.decode(
            raw,
            _PUBLIC_KEY,
            algorithms=["RS256"],
            options={"require": ["iss", "sub", "exp", "iat"]},
        )
    except _JWTError as exc:
        return LicenseInfo(valid=False, message=f"invalid license: {exc}")

    if payload.get("iss") != "opama":
        return LicenseInfo(valid=False, message="invalid issuer")

    modules: list[str] | str = payload.get("modules", "*")
    exp_ts = payload.get("exp")
    expires_at = datetime.fromtimestamp(exp_ts, tz=timezone.utc) if exp_ts else None

    return LicenseInfo(
        valid=True,
        tier=payload.get("tier", "premium"),
        modules=modules,
        customer=payload.get("customer", payload.get("sub", "")),
        expires_at=expires_at,
        message="",
    )


def get_license() -> LicenseInfo:
    """Read OPAMA_LICENSE_KEY from the environment and decode it.

    If the env var is absent or empty, returns a dev-mode info with all
    modules enabled (modules="*") so local development works without a key.
    """
    raw = os.getenv("OPAMA_LICENSE_KEY", "").strip()
    if not raw:
        return LicenseInfo(
            valid=False,
            tier="dev",
            modules="*",
            message="dev mode — all modules enabled",
        )
    return decode_license(raw)
