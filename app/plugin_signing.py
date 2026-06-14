"""
Instance-level RS256 key pair for signing plugin auth tokens.

Each opama instance generates a unique RSA-2048 key pair on first boot.
The public key is exposed at GET /plugin-store/public-key so remote plugin
vendors can verify that proxied requests came from a legitimate instance.

Token format (60-second TTL):
    {
        "iss": "opama",
        "instance_id": "<uuid>",
        "user_id": "<firebase-uid-or-empty>",
        "plugin_id": "<plugin-id>",
        "iat": <unix-ts>,
        "exp": <unix-ts + 60>
    }

The same instance keypair also backs download-install tokens for type=local
plugins (see app/plugin_installer.py:mint_download_token) — a sibling token
shape with `tier` in place of `user_id`, minted via the shared `_sign()` helper
below so both token types share their iss/instance_id/iat/exp boilerplate.

Key persistence:
    Priority: OPAMA_INSTANCE_PRIVATE_KEY env var → /app/config/instance_key.pem file → generate new
    Instance ID: OPAMA_INSTANCE_ID env var → /app/config/instance_id.txt file → generate new UUID
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import load_pem_private_key

_KEY_PATH = Path(os.getenv("OPAMA_INSTANCE_KEY_PATH", "/app/config/instance_key.pem"))
_ID_PATH = Path(os.getenv("OPAMA_INSTANCE_ID_PATH", "/app/config/instance_id.txt"))

# Module-level cache — populated on first call
_private_pem: str | None = None
_public_pem: str | None = None
_instance_id: str | None = None


def _load_or_create_keypair() -> tuple[str, str]:
    """Return (private_key_pem, public_key_pem), generating if needed."""
    global _private_pem, _public_pem
    if _private_pem and _public_pem:
        return _private_pem, _public_pem

    env_key = os.getenv("OPAMA_INSTANCE_PRIVATE_KEY", "").strip()
    if env_key:
        priv_obj = load_pem_private_key(env_key.encode(), password=None)
        pub = priv_obj.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
        _private_pem, _public_pem = env_key, pub
        return _private_pem, _public_pem

    if _KEY_PATH.exists():
        priv_pem = _KEY_PATH.read_text()
        priv_obj = load_pem_private_key(priv_pem.encode(), password=None)
        pub = priv_obj.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
        _private_pem, _public_pem = priv_pem, pub
        return _private_pem, _public_pem

    # Generate a new RSA-2048 key pair
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()
    pub_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()

    _KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _KEY_PATH.write_text(priv_pem)
    _KEY_PATH.chmod(0o600)

    _private_pem, _public_pem = priv_pem, pub_pem
    return _private_pem, _public_pem


def _load_or_create_instance_id() -> str:
    global _instance_id
    if _instance_id:
        return _instance_id

    env_id = os.getenv("OPAMA_INSTANCE_ID", "").strip()
    if env_id:
        _instance_id = env_id
        return _instance_id

    if _ID_PATH.exists():
        _instance_id = _ID_PATH.read_text().strip()
        return _instance_id

    _instance_id = str(uuid.uuid4())
    _ID_PATH.parent.mkdir(parents=True, exist_ok=True)
    _ID_PATH.write_text(_instance_id)
    return _instance_id


def get_public_key_pem() -> str:
    """Return this instance's RSA public key as a PEM string."""
    _, pub = _load_or_create_keypair()
    return pub


def get_instance_id() -> str:
    """Return this instance's persistent UUID."""
    return _load_or_create_instance_id()


def _sign(extra_claims: dict, ttl_seconds: int) -> str:
    """Encode `extra_claims` plus the common iss/instance_id/iat/exp envelope
    as an RS256 JWT signed with this instance's private key.

    Shared by sign_plugin_token (proxy auth, 60s TTL) and
    plugin_installer.mint_download_token (local-install downloads, 15min TTL)
    so the two token shapes don't duplicate the encode/now/exp boilerplate.
    """
    priv_pem, _ = _load_or_create_keypair()
    now = datetime.now(tz=timezone.utc)
    payload = {
        "iss": "opama",
        "instance_id": get_instance_id(),
        "iat": now,
        "exp": now + timedelta(seconds=ttl_seconds),
        **extra_claims,
    }
    return jwt.encode(payload, priv_pem, algorithm="RS256")


def sign_plugin_token(user_id: str, plugin_id: str) -> str:
    """Return a short-lived RS256 JWT authorising a remote plugin request."""
    return _sign({"user_id": user_id, "plugin_id": plugin_id}, ttl_seconds=60)


def _extract_user_id(authorization: str) -> str:
    """Best-effort extraction of user_id from a Firebase Bearer token."""
    if not authorization.startswith("Bearer "):
        return ""
    token = authorization[7:]
    try:
        payload = jwt.decode(token, options={"verify_signature": False}, algorithms=["RS256", "HS256"])
        return payload.get("uid") or payload.get("sub") or ""
    except Exception:
        return ""
