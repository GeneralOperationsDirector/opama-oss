"""
Control-plane HTTP service.

Routes:
  GET  /healthz          — liveness
  GET  /tenants          — inspect provisioned tenants
  POST /billing/webhook  — Stripe webhook: verify → map to a PlanIntent →
                           record synchronously → run the slow provisioner work
                           in a BackgroundTask and return 200 immediately.

Why background work matters: standing up / restarting a tenant container can take
a minute on first boot (alembic + uvicorn), well past Stripe's webhook timeout.
We acknowledge the event fast and reconcile the instance out of band; the Tenant
row's status (provisioning → running | error) reflects the outcome.

Run:  uvicorn control_plane.main:app --port 9000
"""
from __future__ import annotations

import logging

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from sqlmodel import Session, select

from control_plane import tenants
from control_plane.billing.events import PlanIntent, plan_from_event
from control_plane.billing.stripe_webhook import WebhookError, construct_event
from control_plane.db import engine, init_db
from control_plane.models import Tenant
from control_plane.provisioner import ProvisioningError, make_provisioner

log = logging.getLogger("control_plane")

app = FastAPI(title="opama control plane")


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/tenants")
def list_tenants() -> list[dict]:
    with Session(engine) as session:
        rows = session.exec(select(Tenant)).all()
        return [
            {
                "slug": t.slug,
                "email": t.customer_email,
                "status": t.status,
                "instance_url": t.instance_url,
                "stripe_customer_id": t.stripe_customer_id,
                "last_error": t.last_error,
            }
            for t in rows
        ]


# --- background reconcilers (own provisioner + session) -------------------

def _bg_provision(tenant_id: int) -> None:
    try:
        provisioner = make_provisioner()
        tenants.apply_provision(provisioner, tenant_id)
    except ProvisioningError as exc:
        log.error("provision failed for tenant %s: %s", tenant_id, exc)


def _bg_relicense(tenant_id: int) -> None:
    try:
        provisioner = make_provisioner()
        tenants.apply_relicense(provisioner, tenant_id)
    except ProvisioningError as exc:
        log.error("relicense failed for tenant %s: %s", tenant_id, exc)


def _bg_deprovision(tenant_id: int, destroy: bool) -> None:
    try:
        provisioner = make_provisioner()
        tenants.apply_deprovision(provisioner, tenant_id, destroy=destroy)
    except ProvisioningError as exc:
        log.error("deprovision failed for tenant %s: %s", tenant_id, exc)


def _dispatch(intent: PlanIntent, background: BackgroundTasks) -> dict:
    """Record the intent synchronously, schedule the slow work, summarize."""
    with Session(engine) as session:
        if intent.action in ("provision", "relicense"):
            tenant = tenants.upsert_tenant_and_subscription(
                session,
                slug=intent.slug,
                email=intent.email,
                tier=intent.tier,
                modules=intent.modules,
                period_end=intent.period_end,
                stripe_customer_id=intent.stripe_customer_id,
                stripe_subscription_id=intent.stripe_subscription_id,
            )
            # provision vs relicense is decided by whether it's already running,
            # which makes redelivered/created+updated events idempotent.
            if tenant.host_port is None:
                background.add_task(_bg_provision, tenant.id)
                scheduled = "provision"
            else:
                background.add_task(_bg_relicense, tenant.id)
                scheduled = "relicense"
            return {"tenant": tenant.slug, "scheduled": scheduled}

        # deprovision — find by customer; nothing to do if we never saw them.
        if not intent.stripe_customer_id:
            return {"scheduled": "none", "reason": "no customer id"}
        tenant = tenants.find_tenant_by_customer(session, intent.stripe_customer_id)
        if tenant is None:
            return {"scheduled": "none", "reason": "unknown customer"}
        background.add_task(_bg_deprovision, tenant.id, intent.destroy)
        return {"tenant": tenant.slug, "scheduled": "destroy" if intent.destroy else "downgrade"}


@app.post("/billing/webhook")
async def billing_webhook(
    request: Request,
    background: BackgroundTasks,
    stripe_signature: str = Header(default=""),
) -> dict:
    payload = await request.body()
    try:
        event = construct_event(payload, stripe_signature)
    except WebhookError as exc:
        # 400 so Stripe surfaces the failure (and doesn't treat it as delivered).
        raise HTTPException(status_code=400, detail=str(exc))

    intent = plan_from_event(event)
    if intent is None:
        return {"received": True, "ignored": event.get("type")}

    result = _dispatch(intent, background)
    return {"received": True, "type": event.get("type"), **result}
