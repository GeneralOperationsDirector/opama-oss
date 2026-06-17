"""
Tenant lifecycle operations — the domain layer shared by the CLI (manual) and
the Stripe webhook (M3). Both express the same intents; only the trigger differs.

Split into two phases on purpose:
  * record (upsert_tenant_and_subscription) — fast DB writes, safe to do inside a
    webhook request before returning 200.
  * apply_* — the slow infrastructure work (stand up / restart / tear down a
    container, which can take a minute on first boot). The webhook runs these in
    a BackgroundTask; the CLI runs them inline. Each opens its own Session so it's
    independent of the caller's transaction/lifetime.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from control_plane.db import engine
from control_plane.licensing import has_signing_key, mint_for_tenant
from control_plane.models import Subscription, Tenant, TenantStatus
from control_plane.provisioner.base import Provisioner, ProvisioningError


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _get_sub(session: Session, tenant_id: int) -> Subscription | None:
    return session.exec(
        select(Subscription).where(Subscription.tenant_id == tenant_id)
    ).first()


# --- record phase (fast, in-request) --------------------------------------

def upsert_tenant_and_subscription(
    session: Session,
    *,
    slug: str,
    email: str | None,
    tier: str,
    modules: str,
    period_end: datetime,
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
    sub_status: str = "active",
) -> Tenant:
    """Create or update a tenant + its single subscription row. Idempotent — safe
    on Stripe redeliveries."""
    tenant = session.exec(select(Tenant).where(Tenant.slug == slug)).first()
    if tenant is None:
        tenant = Tenant(slug=slug, customer_email=email or "")
    if email:
        tenant.customer_email = email
    if stripe_customer_id:
        tenant.stripe_customer_id = stripe_customer_id
    if tenant.status in (None, TenantStatus.DESTROYED):
        tenant.status = TenantStatus.PROVISIONING
    tenant.updated_at = _now()
    session.add(tenant)
    session.commit()
    session.refresh(tenant)

    sub = _get_sub(session, tenant.id) or Subscription(tenant_id=tenant.id)
    sub.tier = tier
    sub.modules = modules
    sub.status = sub_status
    sub.current_period_end = period_end
    if stripe_subscription_id:
        sub.stripe_subscription_id = stripe_subscription_id
    sub.updated_at = _now()
    session.add(sub)
    session.commit()
    return tenant


def find_tenant_by_customer(session: Session, stripe_customer_id: str) -> Tenant | None:
    return session.exec(
        select(Tenant).where(Tenant.stripe_customer_id == stripe_customer_id)
    ).first()


# --- license resolution ----------------------------------------------------

def _resolve_license(session: Session, tenant: Tenant, explicit_key: str = "") -> tuple[str, str]:
    """Return (OPAMA_LICENSE_KEY, human note). Precedence: explicit key → mint from
    subscription → dev mode (no signing key on disk)."""
    if explicit_key:
        return explicit_key, "explicit key"
    if not has_signing_key():
        return "", "dev mode (no signing key on disk)"
    sub = _get_sub(session, tenant.id)
    if sub is None or sub.current_period_end is None:
        raise ProvisioningError("no subscription / current_period_end to mint a license from")
    note = f"minted ({sub.tier}, modules={sub.modules or 'core-only'})"
    return mint_for_tenant(tenant, sub), note


# --- apply phase (slow, background/inline) ---------------------------------

def apply_provision(provisioner: Provisioner, tenant_id: int, explicit_key: str = "") -> tuple[str, str]:
    """Stand up the tenant's instance. Returns (instance_url, license note).
    Marks the tenant ERROR (and re-raises) on failure."""
    with Session(engine) as session:
        tenant = session.get(Tenant, tenant_id)
        if tenant is None:
            raise ProvisioningError(f"tenant {tenant_id} no longer exists")
        key, note = _resolve_license(session, tenant, explicit_key)
        try:
            handle = provisioner.create(tenant, key)
        except ProvisioningError as exc:
            tenant.status = TenantStatus.ERROR
            tenant.last_error = str(exc)
            tenant.updated_at = _now()
            session.add(tenant)
            session.commit()
            raise
        tenant.container_id = handle.container_id
        tenant.host_port = handle.host_port
        tenant.instance_url = handle.instance_url
        tenant.database_name = handle.database_name
        tenant.status = TenantStatus.RUNNING
        tenant.last_error = None
        tenant.updated_at = _now()
        session.add(tenant)
        session.commit()
        return tenant.instance_url, note


def apply_relicense(provisioner: Provisioner, tenant_id: int, explicit_key: str = "") -> tuple[str, str]:
    """Re-boot the tenant with a freshly resolved license (plan change). Falls back
    to a full provision if the tenant was never stood up."""
    with Session(engine) as session:
        tenant = session.get(Tenant, tenant_id)
        if tenant is None:
            raise ProvisioningError(f"tenant {tenant_id} no longer exists")
        if tenant.host_port is None:
            # Never provisioned (e.g. subscription.updated arrived first) — provision.
            return apply_provision(provisioner, tenant_id, explicit_key)
        key, note = _resolve_license(session, tenant, explicit_key)
        provisioner.update_license(tenant, key)
        tenant.status = TenantStatus.RUNNING
        tenant.updated_at = _now()
        session.add(tenant)
        session.commit()
        return tenant.instance_url, note


def apply_deprovision(provisioner: Provisioner, tenant_id: int, destroy: bool = False) -> None:
    """Handle a cancellation / payment failure.

    destroy=True (or a tenant that was never provisioned) → tear it down. Otherwise
    downgrade to a core-only license and restart, leaving the instance + data in
    place. The downgrade is a real re-mint (tier=core, empty module list) so the
    plugin gate drops every premium router on the next boot."""
    with Session(engine) as session:
        tenant = session.get(Tenant, tenant_id)
        if tenant is None:
            return

        if destroy or tenant.host_port is None:
            provisioner.destroy(tenant)
            tenant.status = TenantStatus.DESTROYED
            tenant.container_id = None
            tenant.host_port = None
            tenant.instance_url = None
            tenant.updated_at = _now()
            session.add(tenant)
            session.commit()
            return

        sub = _get_sub(session, tenant.id) or Subscription(tenant_id=tenant.id)
        sub.tier = "core"
        sub.modules = ""               # empty list claim → only core plugins load
        sub.status = "canceled"
        sub.current_period_end = _now() + timedelta(days=1)  # short, valid core license
        sub.updated_at = _now()
        session.add(sub)
        session.commit()

        key, _ = _resolve_license(session, tenant, "")
        provisioner.update_license(tenant, key)
        tenant.status = TenantStatus.RUNNING
        tenant.updated_at = _now()
        session.add(tenant)
        session.commit()
