"""
Authentication and user management API router.

Endpoints:
- GET /auth/config - Public: which auth provider is active ("local" | "firebase")
- POST /auth/register - Create a local username/password account (AUTH_PROVIDER=local only)
- POST /auth/login - Authenticate a local account, issue a long-lived token (AUTH_PROVIDER=local only)
- GET /auth/me - Get current user profile
- PATCH /auth/me - Update current user profile
- DELETE /auth/me - Delete current user account
"""

import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session
from pydantic import BaseModel

from services.shared.audit import write_audit_log
from services.shared.database import get_session
from services.shared.models import User
from .middleware import get_current_user
from .providers import provider_name
from .providers.local_provider import LocalProvider, credential_for, issue_token

router = APIRouter()

_local_provider = LocalProvider()


class UserProfileResponse(BaseModel):
    """User profile response model."""

    id: int
    firebase_uid: Optional[str]
    auth_provider: str
    email: Optional[str]
    display_name: Optional[str]
    is_admin: bool
    created_at: str
    has_password: bool


class UpdateProfileRequest(BaseModel):
    """Request model for updating user profile."""

    display_name: Optional[str] = None


class AuthConfigResponse(BaseModel):
    """Public auth configuration — tells the frontend which provider is active,
    and whether this instance looks reachable beyond localhost (drives the
    password guardrail nudge → hard-prompt escalation for local accounts)."""

    provider: str
    instance_exposed: bool


class RegisterRequest(BaseModel):
    """Request model for local account registration."""

    username: str
    password: Optional[str] = None
    display_name: Optional[str] = None


class LoginRequest(BaseModel):
    """Request model for local account login."""

    username: str
    password: Optional[str] = None


class TokenResponse(BaseModel):
    """Response for register/login — a long-lived bearer token plus the profile."""

    token: str
    user: UserProfileResponse


class SetPasswordRequest(BaseModel):
    """Request model for setting/changing a local account's password.

    `current_password` is required only when the account already has one —
    passwordless accounts may set their first password directly.
    """

    current_password: Optional[str] = None
    new_password: str


# Loopback hosts that don't count as "exposed beyond this machine."
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1"}


def _is_local_origin(origin: str) -> bool:
    host = origin.split("://", 1)[-1].split(":", 1)[0].strip().lower()
    return host in _LOCAL_HOSTS


def _instance_exposed() -> bool:
    """True if CORS_ORIGINS names any non-loopback origin — our proxy for
    "this instance looks reachable beyond localhost." Drives the password
    guardrail's escalation from a soft nudge to a hard prompt (locked
    decision #2 in the auth_provider_plan memory)."""
    origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
    return any(not _is_local_origin(o) for o in origins)


def _profile(user: User, session: Session) -> UserProfileResponse:
    has_password = True
    if user.auth_provider == "local":
        credential = credential_for(user, session)
        has_password = bool(credential and credential.password_hash)

    return UserProfileResponse(
        id=user.id,
        firebase_uid=user.firebase_uid,
        auth_provider=user.auth_provider,
        email=user.email,
        display_name=user.display_name or user.nickname,
        is_admin=user.is_admin,
        created_at=user.created_at.isoformat(),
        has_password=has_password,
    )


@router.get("/config", response_model=AuthConfigResponse)
async def get_auth_config():
    """Public — which auth provider this instance is running, so the frontend
    can render the matching login UI (username/password vs. Firebase), plus
    whether the instance looks externally reachable (guardrail escalation)."""
    return AuthConfigResponse(provider=provider_name(), instance_exposed=_instance_exposed())


def _require_local_auth() -> None:
    if provider_name() != "local":
        raise HTTPException(
            status_code=400,
            detail="Local accounts are not enabled on this instance (AUTH_PROVIDER is not \"local\")",
        )


@router.post("/register", response_model=TokenResponse)
async def register_local_account(
    body: RegisterRequest,
    session: Session = Depends(get_session),
):
    """Create a local username/password account and sign the user in immediately."""
    _require_local_auth()

    username = body.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")

    try:
        user = _local_provider.register(username, body.password, body.display_name, session)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return TokenResponse(token=issue_token(username), user=_profile(user, session))


@router.post("/login", response_model=TokenResponse)
async def login_local_account(
    body: LoginRequest,
    session: Session = Depends(get_session),
):
    """Authenticate a local account and issue a long-lived bearer token."""
    _require_local_auth()

    username = body.username.strip()
    try:
        user = _local_provider.authenticate(username, body.password, session)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    return TokenResponse(token=issue_token(username), user=_profile(user, session))


@router.post("/set-password", response_model=UserProfileResponse)
async def set_local_password(
    body: SetPasswordRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Set or change the current user's local-account password.

    Passwordless accounts may set their first password directly; accounts
    that already have one must supply the correct current password. Local
    accounts only — see [[auth_provider_plan]] guardrail design (locked
    decision #2: nudge passwordless accounts toward setting one).
    """
    _require_local_auth()
    if current_user.auth_provider != "local":
        raise HTTPException(status_code=400, detail="This account is not a local account")

    had_password = bool(
        (cred := credential_for(current_user, session)) and cred.password_hash
    )

    try:
        _local_provider.set_password(current_user, body.current_password, body.new_password, session)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    write_audit_log(
        session,
        action="auth.password_set",
        user=current_user,
        target=f"user:{current_user.id}",
        request=request,
        detail="changed password" if had_password else "set initial password",
    )

    return _profile(current_user, session)


@router.get("/me", response_model=UserProfileResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    Get the current authenticated user's profile.

    Returns:
        UserProfileResponse: User profile data
    """
    return _profile(current_user, session)


@router.patch("/me", response_model=UserProfileResponse)
async def update_current_user_profile(
    updates: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    Update the current authenticated user's profile.

    Args:
        updates: Profile updates
        current_user: Authenticated user
        session: Database session

    Returns:
        UserProfileResponse: Updated user profile
    """
    if updates.display_name is not None:
        current_user.display_name = updates.display_name

    session.add(current_user)
    session.commit()
    session.refresh(current_user)

    return _profile(current_user, session)


@router.delete("/me")
async def delete_current_user_account(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """
    Delete the current authenticated user's account.

    WARNING: This will delete all user data including inventory, decks, and sales history.

    Returns:
        dict: Success message
    """
    # FK-safe delete: LocalCredential has no CASCADE, so it must go before
    # the parent User row (see "FK-safe deletes" in CLAUDE.md).
    if current_user.auth_provider == "local":
        credential = credential_for(current_user, session)
        if credential:
            session.delete(credential)
            session.flush()

    session.delete(current_user)
    session.commit()

    return {
        "success": True,
        "message": "Account deleted successfully",
    }
