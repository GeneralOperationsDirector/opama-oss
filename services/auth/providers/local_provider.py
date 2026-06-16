# app/services/auth/providers/local_provider.py
"""
LocalProvider — username/password accounts for self-hosted instances.

Issues long-lived opama-signed JWTs (HS256, signed with `LOCAL_AUTH_SECRET`)
on register/login; `resolve_user` verifies those tokens on each request and
looks the account up via `LocalCredential`.

Long-lived-with-no-refresh is a deliberate choice for the low-friction,
single-user "command station" use case the OSS edition targets — the threat
model for a localhost-bound box is very different from multi-tenant cloud.
Short-lived tokens, refresh, device management, and expiry policy belong in
a future "Sessions & Security" plugin, not core. See auth_provider_plan memory.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from sqlmodel import Session, select

from services.shared.models import LocalCredential, User

from .base import AuthProvider, resolve_is_admin

_ALGORITHM = "HS256"
_TOKEN_TTL_DAYS = int(os.getenv("LOCAL_AUTH_TOKEN_TTL_DAYS", "365"))


def _secret() -> str:
    secret = os.getenv("LOCAL_AUTH_SECRET", "")
    if not secret:
        raise RuntimeError(
            "LOCAL_AUTH_SECRET must be set when AUTH_PROVIDER=local — it signs "
            "local-account tokens. Generate one with `openssl rand -hex 32` and "
            "keep it stable across restarts (changing it invalidates all tokens)."
        )
    return secret


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: Optional[str]) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def issue_token(username: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": username, "iat": now, "exp": now + timedelta(days=_TOKEN_TTL_DAYS)}
    return jwt.encode(payload, _secret(), algorithm=_ALGORITHM)


def _lookup(username: str, session: Session) -> Optional[tuple[LocalCredential, User]]:
    return session.exec(
        select(LocalCredential, User)
        .where(LocalCredential.username == username)
        .where(LocalCredential.user_id == User.id)
    ).first()


def credential_for(user: User, session: Session) -> Optional[LocalCredential]:
    return session.exec(
        select(LocalCredential).where(LocalCredential.user_id == user.id)
    ).first()


class LocalProvider(AuthProvider):
    name = "local"

    def resolve_user(self, token: str, session: Session) -> User:
        try:
            payload = jwt.decode(token, _secret(), algorithms=[_ALGORITHM])
        except jwt.PyJWTError as exc:
            raise ValueError(f"Invalid or expired token: {exc}") from exc

        username = payload.get("sub")
        if not username:
            raise ValueError("Token missing subject")

        row = _lookup(username, session)
        if not row:
            raise ValueError("Account no longer exists")

        _credential, user = row
        return user

    def register(
        self,
        username: str,
        password: Optional[str],
        display_name: Optional[str],
        session: Session,
    ) -> User:
        """Create a new local account. Raises ValueError if the username is taken."""
        existing = session.exec(
            select(LocalCredential).where(LocalCredential.username == username)
        ).first()
        if existing:
            raise ValueError("Username is already taken")

        user = User(
            auth_provider="local",
            display_name=display_name,
            is_admin=resolve_is_admin(None, session),
        )
        session.add(user)
        session.flush()  # populate user.id for the FK below, in the same transaction

        now = datetime.utcnow()
        credential = LocalCredential(
            user_id=user.id,
            username=username,
            password_hash=hash_password(password) if password else None,
            password_set_at=now if password else None,
        )
        session.add(credential)
        session.commit()
        session.refresh(user)
        return user

    def set_password(
        self,
        user: User,
        current_password: Optional[str],
        new_password: str,
        session: Session,
    ) -> None:
        """Set or change a local account's password.

        Passwordless accounts may set one directly. Accounts that already
        have a password must supply the correct current one — this is the
        same "set or change" endpoint either way. Raises ValueError on bad
        input or a failed current-password check.
        """
        if not new_password:
            raise ValueError("New password is required")

        credential = credential_for(user, session)
        if not credential:
            raise ValueError("Account has no local credential record")

        if credential.password_hash:
            if not current_password or not verify_password(current_password, credential.password_hash):
                raise ValueError("Current password is incorrect")

        credential.password_hash = hash_password(new_password)
        credential.password_set_at = datetime.utcnow()
        session.add(credential)
        session.commit()

    def authenticate(self, username: str, password: Optional[str], session: Session) -> User:
        """Verify username/password and return the matching User. Raises ValueError on failure."""
        row = _lookup(username, session)
        if not row:
            raise ValueError("Invalid username or password")

        credential, user = row
        if credential.password_hash:
            if not password or not verify_password(password, credential.password_hash):
                raise ValueError("Invalid username or password")
        # Password-less accounts accept any login by username alone — the
        # frontend nudges (and eventually requires) setting a password before
        # the instance is reachable beyond localhost.

        return user
