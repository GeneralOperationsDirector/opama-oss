"""
Pool billing webhook route.

``POST /billing/webhook`` is the SaaS entrypoint Stripe calls on subscription
lifecycle changes. It is unauthenticated by design — trust comes from the HMAC
signature verification (``construct_event``), not a bearer token — and it flips
the caller's Organization plan columns that ``require_tier()`` reads per request.

Always mounted, but inert until ``STRIPE_WEBHOOK_SECRET`` is set (an unconfigured
or unsigned request gets a 400). Unmatched events return 200 so Stripe stops
retrying a customer we don't know about.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session

from services.shared.database import get_session
from services.shared.models import User, ORG_ROLE_OWNER
from services.auth.middleware import get_current_user
from services.auth.org_context import OrgContext, require_org_role

from . import config
from .checkout import CheckoutError, create_checkout_session
from .events import plan_from_event
from .service import apply_plan_update
from .webhook import WebhookError, construct_event

log = logging.getLogger("uvicorn.error")

router = APIRouter()


@router.get("/config")
def billing_config():
    """Public: whether hosted billing/checkout is configured for this instance.

    The frontend uses this to decide whether to show upgrade UI at all, so an
    OSS/self-host instance (no Stripe keys) never shows a meaningless "Upgrade".
    """
    return {"enabled": config.checkout_enabled()}


class CheckoutRequest(BaseModel):
    tier: str = "premium"
    price_id: Optional[str] = None


@router.post("/checkout")
def create_checkout(
    body: CheckoutRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    ctx: OrgContext = Depends(require_org_role(ORG_ROLE_OWNER)),
):
    """Create a Stripe Checkout Session for the active org (owner only) and return
    its redirect URL. Subscribing is an org-level (billing-owner) action."""
    origin = request.headers.get("origin") or request.headers.get("referer") or ""
    try:
        url = create_checkout_session(
            org_id=ctx.org_id,
            tier=body.tier,
            price_id=body.price_id,
            customer_id=ctx.org.stripe_customer_id,
            customer_email=current_user.email,
            success_url=config.checkout_success_url(origin),
            cancel_url=config.checkout_cancel_url(origin),
        )
    except CheckoutError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"url": url}


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    session: Session = Depends(get_session),
):
    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature", "")

    try:
        event = construct_event(payload, sig_header)
    except WebhookError as exc:
        # 400 → Stripe marks the delivery failed and retries (transient misconfig)
        # without us acting on an unverified payload.
        raise HTTPException(status_code=400, detail=str(exc))

    update = plan_from_event(event)
    if update is None:
        return {"status": "ignored", "type": event.get("type")}

    result = apply_plan_update(update, session)
    if result.status == "unmatched":
        log.warning(
            "billing webhook %s: no org for customer=%s org_id=%s",
            event.get("type"),
            update.stripe_customer_id,
            update.org_id,
        )
    return {"status": result.status, "org_id": result.org_id}
