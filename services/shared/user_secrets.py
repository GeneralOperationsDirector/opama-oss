"""
Helper API for services.shared.models_security.UserSecret.

UserSecret is a generic per-(user_id, service) encrypted vault that has
existed since the security-tables migration but had no callers. This module
is the first real usage — wraps it with the same encrypt/hint conventions
app/secrets.py already establishes for StorefrontSettings.github_token and
similar ad-hoc encrypted columns. See docs/MODULE_DEVELOPMENT.md §4(A).

`service` is a free-form slug, e.g. f"{plugin_id}_access_token".
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session, select

from app.secrets import encrypt_secret, decrypt_secret_safe, secret_hint
from services.shared.models_security import UserSecret


def _get_row(session: Session, user_id: int, service: str) -> Optional[UserSecret]:
    return session.exec(
        select(UserSecret).where(
            UserSecret.user_id == user_id,
            UserSecret.service == service,
        )
    ).first()


def get_user_secret(session: Session, user_id: int, service: str) -> Optional[str]:
    """Return the decrypted secret, or None if not set."""
    row = _get_row(session, user_id, service)
    if row is None:
        return None
    plaintext = decrypt_secret_safe(row.encrypted_value)
    row.last_used_at = datetime.now(timezone.utc)
    session.add(row)
    session.commit()
    return plaintext


def set_user_secret(session: Session, user_id: int, service: str, plaintext: str) -> None:
    """Encrypt and upsert a secret."""
    row = _get_row(session, user_id, service)
    encrypted = encrypt_secret(plaintext)
    hint = secret_hint(plaintext)
    now = datetime.now(timezone.utc)
    if row is None:
        row = UserSecret(
            user_id=user_id,
            service=service,
            encrypted_value=encrypted,
            hint=hint,
            created_at=now,
            updated_at=now,
        )
    else:
        row.encrypted_value = encrypted
        row.hint = hint
        row.updated_at = now
    session.add(row)
    session.commit()


def delete_user_secret(session: Session, user_id: int, service: str) -> None:
    row = _get_row(session, user_id, service)
    if row is not None:
        session.delete(row)
        session.commit()


def user_secret_status(session: Session, user_id: int, service: str) -> tuple[bool, Optional[str]]:
    """Return (is_set, hint) without decrypting the secret."""
    row = _get_row(session, user_id, service)
    if row is None:
        return False, None
    return True, row.hint
