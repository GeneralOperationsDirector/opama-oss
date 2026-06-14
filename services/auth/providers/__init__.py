# app/services/auth/providers/__init__.py
"""
Auth provider selection.

`AUTH_PROVIDER` env var picks the active provider:
- "local"    — username/password accounts, opama-issued tokens (OSS default)
- "firebase" — Firebase ID tokens (existing dev + cloud accounts)

Defaults to "local" so a freshly self-hosted instance works with zero external
setup. Existing Firebase-backed deployments must pin AUTH_PROVIDER=firebase
explicitly (already set in this repo's .env.local) to keep current behavior.
"""
from __future__ import annotations

import os

from .base import AuthProvider
from .firebase_provider import FirebaseProvider
from .local_provider import LocalProvider

__all__ = ["AuthProvider", "FirebaseProvider", "LocalProvider", "get_auth_provider", "provider_name"]

_FIREBASE = FirebaseProvider()
_LOCAL = LocalProvider()


def provider_name() -> str:
    return os.getenv("AUTH_PROVIDER", "local").strip().lower()


def get_auth_provider() -> AuthProvider:
    """Return the active AuthProvider instance, selected by AUTH_PROVIDER."""
    return _FIREBASE if provider_name() == "firebase" else _LOCAL
