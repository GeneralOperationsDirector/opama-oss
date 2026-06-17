"""
Active-organization resolution for the shared-DB "pool" tenancy model.

Every request runs in the context of one Organization — the unit that *owns*
collection data and *holds* the subscription/entitlement (see the pool_vs_silo
design memory). A solo collector is an "org-of-one"; a store owner's staff all
act inside the store's org. This module turns the authenticated `User` into the
`OrgContext` (org + the caller's role in it) the rest of the app scopes by.

Resolution order for the active org:
  1. An explicit `X-Org-Id` request header — used only if the caller is a member
     of that org (else 403); lets a user with multiple memberships pick one.
  2. The caller's personal org (is_personal=true).
  3. The caller's lowest-id membership (deterministic fallback).

Self-healing: a user with zero memberships (e.g. created before signup wired in
org creation) gets a personal org-of-one lazily. `ensure_personal_org()` is the
reusable entry point signup paths can call eagerly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlmodel import Session, select

from services.shared.database import get_session
from services.shared.models import (
    Membership,
    Organization,
    User,
    ORG_ROLE_OWNER,
    ORG_ROLE_RANK,
)
from services.shared.rls import stamp_session_org

from .middleware import get_current_user


@dataclass
class OrgContext:
    """The active organization for a request plus the caller's role in it."""

    org: Organization
    role: str

    @property
    def org_id(self) -> int:
        return self.org.id

    def has_role(self, minimum: str) -> bool:
        """True if the caller's role is at least `minimum` (owner>manager>staff)."""
        return ORG_ROLE_RANK.get(self.role, -1) >= ORG_ROLE_RANK.get(minimum, 999)


def _unique_personal_slug(user: User, session: Session) -> str:
    """A free, deterministic slug for a user's personal org (`user-<id>`)."""
    base = f"user-{user.id}"
    slug = base
    n = 1
    while session.exec(select(Organization).where(Organization.slug == slug)).first():
        n += 1
        slug = f"{base}-{n}"
    return slug


def ensure_personal_org(user: User, session: Session) -> Organization:
    """
    Return the user's personal org, creating an org-of-one (+ owner Membership)
    if they have none. Idempotent: if a personal membership already exists it is
    returned unchanged.
    """
    existing = session.exec(
        select(Organization)
        .join(Membership, Membership.org_id == Organization.id)
        .where(Membership.user_id == user.id, Organization.is_personal == True)  # noqa: E712
        .order_by(Organization.id)
    ).first()
    if existing:
        return existing

    name = (
        user.display_name
        or user.nickname
        or (user.email.split("@")[0] if user.email else None)
        or f"Collection {user.id}"
    )
    org = Organization(name=name, slug=_unique_personal_slug(user, session), is_personal=True)
    session.add(org)
    session.commit()
    session.refresh(org)

    session.add(Membership(org_id=org.id, user_id=user.id, role=ORG_ROLE_OWNER))
    session.commit()
    return org


def list_user_orgs(user: User, session: Session) -> list[tuple[Organization, str]]:
    """All orgs `user` belongs to, each paired with their role, personal org first.

    The backing list for an org switcher: the caller picks one and sends its id as
    `X-Org-Id` on subsequent requests (see `get_current_org`). Ordered personal-org
    first, then by id, so the default active org sorts to the top.
    """
    rows = session.exec(
        select(Organization, Membership.role)
        .join(Membership, Membership.org_id == Organization.id)
        .where(Membership.user_id == user.id)
        .order_by(Organization.is_personal.desc(), Organization.id)  # noqa: E712
    ).all()
    return [(org, role) for org, role in rows]


def resolve_org_context(
    user: User,
    session: Session,
    requested_org_id: Optional[int] = None,
) -> OrgContext:
    """Resolve the active OrgContext for `user` (no FastAPI types).

    Side effect: stamps the active org onto `session` for RLS (`stamp_session_org`),
    so the per-request Postgres GUC `app.current_org_id` is set. This is the single
    choke point shared by the HTTP dependency (`get_current_org`) and non-HTTP
    callers (MCP tools via `resolve_org_context`), so every scoped query runs under
    the right RLS org regardless of entry path.
    """

    def _ctx(org: Organization, role: str) -> OrgContext:
        stamp_session_org(session, org.id)
        return OrgContext(org=org, role=role)

    memberships = session.exec(
        select(Membership).where(Membership.user_id == user.id)
    ).all()

    if not memberships:
        org = ensure_personal_org(user, session)
        return _ctx(org, ORG_ROLE_OWNER)

    by_org = {m.org_id: m for m in memberships}

    if requested_org_id is not None:
        membership = by_org.get(requested_org_id)
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a member of the requested organization",
            )
    else:
        # Prefer the personal org; else the lowest-id membership (deterministic).
        org_ids = list(by_org.keys())
        personal = session.exec(
            select(Organization.id)
            .where(Organization.id.in_(org_ids), Organization.is_personal == True)  # noqa: E712
            .order_by(Organization.id)
        ).first()
        chosen_org_id = personal if personal is not None else min(org_ids)
        membership = by_org[chosen_org_id]

    org = session.get(Organization, membership.org_id)
    if org is None:
        # Membership pointing at a deleted org — fall back to a personal org.
        org = ensure_personal_org(user, session)
        return _ctx(org, ORG_ROLE_OWNER)
    return _ctx(org, membership.role)


async def get_current_org(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    x_org_id: Optional[int] = Header(None, alias="X-Org-Id"),
) -> OrgContext:
    """FastAPI dependency: the active OrgContext for the authenticated request."""
    return resolve_org_context(current_user, session, requested_org_id=x_org_id)


async def get_current_org_id(
    ctx: OrgContext = Depends(get_current_org),
) -> int:
    """Convenience dependency for handlers that only need the active org id."""
    return ctx.org_id


def require_org_role(minimum: str):
    """
    Dependency factory: require the caller to hold at least `minimum` role
    (owner > manager > staff) in the active org. Returns the OrgContext.
    """

    async def _dep(ctx: OrgContext = Depends(get_current_org)) -> OrgContext:
        if not ctx.has_role(minimum):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires '{minimum}' role in this organization",
            )
        return ctx

    return _dep
