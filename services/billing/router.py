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

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session

from services.shared.database import get_session

from .events import plan_from_event
from .service import apply_plan_update
from .webhook import WebhookError, construct_event

log = logging.getLogger("uvicorn.error")

router = APIRouter()


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
