# app/services/auth/providers/base.py
"""
Pluggable authentication provider interface.

Each provider resolves a verified Bearer token to an opama `User` row. The
active provider is selected by the `AUTH_PROVIDER` env var ("local" |
"firebase") in `services.auth.providers.get_auth_provider`. See the
auth_provider_plan memory for the full design and rationale.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Optional

from sqlmodel import Session, func, select

from services.shared.models import User

# Comma-separated list of emails that are always granted admin on first
# login/registration. If empty, the very first user created on the instance
# becomes admin — convenient for a freshly self-hosted, single-user instance.
ADMIN_EMAILS: set[str] = {
    e.strip().lower()
    for e in os.getenv("ADMIN_EMAILS", "").split(",")
    if e.strip()
}


def resolve_is_admin(email: Optional[str], session: Session) -> bool:
    """True if this email is in ADMIN_EMAILS, or if no users exist yet (first user)."""
    if ADMIN_EMAILS:
        return bool(email and email.lower() in ADMIN_EMAILS)
    count = session.exec(select(func.count()).select_from(User)).one()
    return count == 0


class AuthProvider(ABC):
    """Resolves a Bearer token to an opama `User` row."""

    name: str

    @abstractmethod
    def resolve_user(self, token: str, session: Session) -> User:
        """Verify `token` and return the matching `User`.

        Raises ValueError if the token is invalid/expired, or no matching
        account exists for it (provider-specific: Firebase auto-provisions
        on first login; local accounts must be registered first).
        """
