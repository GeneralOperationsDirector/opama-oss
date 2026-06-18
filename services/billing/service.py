"""
Apply a ``PlanUpdate`` to the Organization it concerns.

Resolution: prefer the org already linked to the Stripe customer; otherwise, on
the first event for a new subscriber, fall back to the ``org_id`` carried on the
Checkout (client_reference_id / metadata) and link the customer id for every
event after. An event that matches no org is reported as ``unmatched`` (logged
by the route, returned 200 so Stripe doesn't retry forever).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
from typing import Optional

from sqlmodel import Session, select

from services.shared.models import Organization

from .events import PlanUpdate


@dataclass
class ApplyResult:
    status: str            # "updated" | "unmatched"
    org_id: Optional[int]


def _resolve_org(update: PlanUpdate, session: Session) -> Optional[Organization]:
    if update.stripe_customer_id:
        org = session.exec(
            select(Organization).where(
                Organization.stripe_customer_id == update.stripe_customer_id
            )
        ).first()
        if org:
            return org
    if update.org_id is not None:
        return session.get(Organization, update.org_id)
    return None


def apply_plan_update(update: PlanUpdate, session: Session) -> ApplyResult:
    org = _resolve_org(update, session)
    if org is None:
        return ApplyResult("unmatched", None)

    org.plan_status = update.status
    if update.tier is not None:
        org.plan_tier = update.tier
    if update.modules is not None:
        org.plan_modules = update.modules
    if update.period_end is not None:
        # Store as naive UTC to match the column (the rest of the app uses
        # naive datetime.utcnow()).
        end = update.period_end
        if end.tzinfo is not None:
            end = end.astimezone(timezone.utc).replace(tzinfo=None)
        org.current_period_end = end
    # Link the customer id on the first event for a new subscriber.
    if update.stripe_customer_id and not org.stripe_customer_id:
        org.stripe_customer_id = update.stripe_customer_id

    session.add(org)
    session.commit()
    session.refresh(org)
    return ApplyResult("updated", org.id)
