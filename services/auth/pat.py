"""
Personal access token (PAT) authentication.

This is additive, not a `resolve_user`/AuthProvider branch — PATs identify
an *agent* connected to a user's account (e.g. Claude Code via MCP), not the
user's own browser session. Only services/ai_assistant/router.py's MCP
endpoint depends on get_user_from_pat; everything else (including
/ai-assistant/chat and /ai-assistant/tokens) keeps using
services.auth.middleware.get_current_user.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Header, status
from sqlmodel import Session, select

from app.secrets import token_digest
from services.shared.database import get_session
from services.shared.models import User
from services.shared.models_security import ApiToken


async def get_user_from_pat(
    authorization: Optional[str] = Header(None),
    session: Session = Depends(get_session),
) -> User:
    """
    Resolve a user from a `Bearer opat_...` personal access token.

    401 on a missing/malformed header, an unknown/revoked token, or a token
    whose owning user no longer exists. Bumps `last_used_at` on success.
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

    digest = token_digest(token.strip())
    row = session.exec(
        select(ApiToken).where(ApiToken.token_hash == digest, ApiToken.revoked_at == None)  # noqa: E711
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = session.get(User, row.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token owner no longer exists",
            headers={"WWW-Authenticate": "Bearer"},
        )

    row.last_used_at = datetime.now(timezone.utc)
    session.add(row)
    session.commit()

    return user
