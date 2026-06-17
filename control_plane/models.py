"""
Control-plane data model (SQLModel) — lives in the control plane's OWN database,
never a tenant's.

A Tenant is one provisioned opama instance (one container + one database in the
Docker driver; one Fly app + Fly Postgres in the Fly driver). A Subscription is
the Stripe-side state that drives what license the tenant's instance carries.

The license itself is NOT stored here — it's minted on demand (M2) and injected
as the OPAMA_LICENSE_KEY env var at provision/restart time. The tenant validates
it offline against the public key embedded in app/license.py.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class TenantStatus:
    """String status values for Tenant.status (kept as plain strings, like the
    rest of opama, rather than a DB enum — easier to evolve without migrations)."""
    PROVISIONING = "provisioning"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    DESTROYED = "destroyed"


class Tenant(SQLModel, table=True):
    """One provisioned opama instance."""

    __tablename__ = "tenant"

    id: Optional[int] = Field(default=None, primary_key=True)

    # URL-safe identifier, also used to name the container/database/subdomain.
    slug: str = Field(index=True, unique=True)
    customer_email: str = Field(index=True)

    # Stripe linkage (populated by the webhook handler in M3).
    stripe_customer_id: Optional[str] = Field(default=None, index=True)

    # Where the instance lives. Driver-agnostic: container_id is set by the
    # Docker driver; a Fly driver would store its machine id here instead.
    container_id: Optional[str] = None
    host_port: Optional[int] = None
    instance_url: Optional[str] = None
    database_name: Optional[str] = None

    status: str = Field(default=TenantStatus.PROVISIONING, index=True)
    last_error: Optional[str] = None

    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class Subscription(SQLModel, table=True):
    """Stripe-side subscription state for a tenant.

    `modules` mirrors the license JWT `modules` claim: "*" for tier-based
    access or a comma-separated allow-list of plugin IDs. `current_period_end`
    becomes the minted license's `exp` (M2), so a lapsed subscription degrades
    the instance to core-only at its next restart.
    """

    __tablename__ = "subscription"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)

    stripe_subscription_id: Optional[str] = Field(default=None, index=True)
    tier: str = Field(default="premium")          # core | free | premium | enterprise
    modules: str = Field(default="*")             # "*" or "ai,grading,portfolio"
    status: str = Field(default="active")         # active | past_due | canceled
    current_period_end: Optional[datetime] = None

    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
