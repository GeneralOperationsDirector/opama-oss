"""
Authentication middleware and dependencies for FastAPI.

Provides authentication dependency injection for protected routes. Token
verification and user resolution are delegated to the active AuthProvider
(selected by the AUTH_PROVIDER env var — see services.auth.providers).
"""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Header, status
from sqlmodel import Session

from services.shared.database import get_session
from services.shared.models import User

from .providers import get_auth_provider


async def get_current_user(
    authorization: Optional[str] = Header(None),
    session: Session = Depends(get_session),
) -> User:
    """
    Dependency to get the current authenticated user.

    Extracts the Bearer token from the Authorization header and hands it to
    the active AuthProvider, which verifies it and resolves (or, for Firebase,
    auto-provisions) the corresponding `User` row.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        scheme, token = authorization.split(" ", 1)
        if scheme.lower() != "bearer":
            raise ValueError("Invalid authentication scheme")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return get_auth_provider().resolve_user(token, session)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_optional_user(
    authorization: Optional[str] = Header(None),
    session: Session = Depends(get_session),
) -> Optional[User]:
    """Return the authenticated user or None — for endpoints that work either way."""
    if not authorization:
        return None
    try:
        return await get_current_user(authorization, session)
    except HTTPException:
        return None


async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Dependency that requires the authenticated user to be an admin."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user
