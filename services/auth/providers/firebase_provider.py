# app/services/auth/providers/firebase_provider.py
"""
FirebaseProvider — Firebase ID token verification with auto-provisioning.

This is the existing auth flow (previously inlined in `middleware.py`),
wrapped behind the `AuthProvider` interface verbatim so that switching
`AUTH_PROVIDER` away from "firebase" is a no-op for existing accounts.
"""
from __future__ import annotations

from sqlmodel import Session, select

from services.shared.models import User

from ..firebase_admin import verify_id_token
from .base import ADMIN_EMAILS, AuthProvider, resolve_is_admin


class FirebaseProvider(AuthProvider):
    name = "firebase"

    def resolve_user(self, token: str, session: Session) -> User:
        decoded = verify_id_token(token)  # raises ValueError on invalid/expired token
        firebase_uid = decoded["uid"]
        email = decoded.get("email")

        user = session.exec(select(User).where(User.firebase_uid == firebase_uid)).first()
        if not user:
            user = User(
                firebase_uid=firebase_uid,
                auth_provider="firebase",
                email=email,
                display_name=decoded.get("name"),
                is_admin=resolve_is_admin(email, session),
            )
            session.add(user)
            session.commit()
            session.refresh(user)
        elif email and ADMIN_EMAILS and email.lower() in ADMIN_EMAILS and not user.is_admin:
            # Promote existing user if they appear in ADMIN_EMAILS but weren't admin yet
            user.is_admin = True
            session.add(user)
            session.commit()
            session.refresh(user)

        return user
