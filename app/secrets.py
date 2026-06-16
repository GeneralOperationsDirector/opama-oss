"""
opama secret encryption — AES-256-GCM for secrets stored in the database.

Usage:
    from app.secrets import encrypt_secret, decrypt_secret, secret_hint

    # Store:
    encrypted = encrypt_secret("ghp_mytoken")
    db_row.github_token = encrypted

    # Read:
    plaintext = decrypt_secret(db_row.github_token)

Key management (priority order):
  1. OPAMA_SECRET_KEY env var — base64url-encoded 32-byte key.
  2. /app/config/secret_key.b64 — auto-generated on first run, persisted.

Generate a key for production:
    python3 -c "import os, base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
    # Then set OPAMA_SECRET_KEY=<output> in your .env.local
"""
from __future__ import annotations

import base64
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

_KEY_FILE = Path("/app/config/secret_key.b64")
_cached_key: bytes | None = None


def _load_key() -> bytes:
    global _cached_key
    if _cached_key is not None:
        return _cached_key

    raw = os.environ.get("OPAMA_SECRET_KEY", "").strip()
    if raw:
        key = base64.urlsafe_b64decode(raw + "==")
        if len(key) != 32:
            raise RuntimeError(
                "OPAMA_SECRET_KEY must be a 32-byte base64url-encoded string. "
                "Generate one with: python3 -c \"import os,base64; "
                "print(base64.urlsafe_b64encode(os.urandom(32)).decode())\""
            )
        _cached_key = key
        return _cached_key

    # Auto-generate and persist key (self-hosted convenience)
    _KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if _KEY_FILE.exists():
        _cached_key = base64.urlsafe_b64decode(_KEY_FILE.read_text().strip() + "==")
        return _cached_key

    new_key = os.urandom(32)
    _KEY_FILE.write_text(base64.urlsafe_b64encode(new_key).decode())
    _KEY_FILE.chmod(0o600)
    log.warning(
        "OPAMA_SECRET_KEY not set — auto-generated a key at %s. "
        "Set OPAMA_SECRET_KEY in production to make this portable.",
        _KEY_FILE,
    )
    _cached_key = new_key
    return _cached_key


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a plaintext secret. Returns a base64url string (nonce + ciphertext + tag)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(12)
    ct = AESGCM(_load_key()).encrypt(nonce, plaintext.encode("utf-8"), b"opama-secret")
    return base64.urlsafe_b64encode(nonce + ct).decode()


def decrypt_secret(token: str) -> str:
    """Decrypt a value produced by encrypt_secret(). Raises ValueError on failure."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    try:
        raw = base64.urlsafe_b64decode(token + "==")
    except Exception:
        raise ValueError("Invalid encrypted secret format")

    if len(raw) < 28:  # 12 nonce + at least 1 byte pt + 16 GCM tag
        raise ValueError("Encrypted secret too short")

    nonce, ct = raw[:12], raw[12:]
    try:
        return AESGCM(_load_key()).decrypt(nonce, ct, b"opama-secret").decode("utf-8")
    except Exception:
        raise ValueError("Secret decryption failed — wrong key or corrupted data")


def decrypt_secret_safe(token: str) -> str:
    """
    Decrypt a secret, falling back to returning the raw value if decryption fails.

    Used for migrating plaintext values that predate encryption. On next save
    the value will be re-encrypted automatically.
    """
    if not token:
        return token
    try:
        return decrypt_secret(token)
    except ValueError:
        return token  # assume plaintext (pre-encryption migration)


def secret_hint(plaintext: str) -> str:
    """Return the last 4 characters for display ('…a4f2'), or None if too short."""
    if len(plaintext) >= 4:
        return f"…{plaintext[-4:]}"
    return "…"


def token_digest(token: str) -> str:
    """HMAC-SHA256 hex digest of a personal access token, keyed by the same
    key encrypt_secret() uses — rotating OPAMA_SECRET_KEY invalidates PATs
    consistently with other secrets. Used so ApiToken.token_hash can be
    looked up without storing the raw token."""
    import hashlib
    import hmac

    return hmac.new(_load_key(), token.encode("utf-8"), hashlib.sha256).hexdigest()
