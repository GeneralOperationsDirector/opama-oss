"""
The Provisioner abstraction.

Every action the control plane takes against a tenant's *infrastructure* goes
through this interface, so the orchestration logic (webhook → mint → provision →
restart) is identical whether the backend is local Docker or Fly. Adding Fly
later (M5) means writing one more subclass — the webhook handler doesn't change.

Entitlement model: a tenant's enabled plugins are determined entirely by the
OPAMA_LICENSE_KEY it boots with (opama's plugin_loader.resolve_enabled reads it
at startup). So "change a plan" == "restart with a new license key" — there is
deliberately no separate runtime entitlement channel. update_license() encodes
exactly that.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from control_plane.models import Tenant


class ProvisioningError(RuntimeError):
    """Raised when a driver cannot complete an infrastructure action."""


@dataclass
class InstanceHandle:
    """What a driver returns after standing an instance up.

    Driver-agnostic: `container_id` is the Docker container id or the Fly
    machine id. The control plane persists these onto the Tenant row.
    """
    container_id: str
    host_port: int
    instance_url: str
    database_name: str


@dataclass
class InstanceStatus:
    running: bool
    healthy: bool          # /healthz returned 200
    detail: str = ""


class Provisioner(ABC):
    """Stand up / tear down / inspect a single tenant's opama instance."""

    @abstractmethod
    def create(self, tenant: Tenant, license_key: str) -> InstanceHandle:
        """Provision datastore + instance for `tenant`, booting it with
        `license_key` as OPAMA_LICENSE_KEY. An empty key boots the instance in
        opama's dev mode (all modules enabled) — useful for M1 smoke tests
        before minting (M2) is wired in. Blocks until the instance is healthy
        or raises ProvisioningError on timeout."""

    @abstractmethod
    def update_license(self, tenant: Tenant, license_key: str) -> None:
        """Re-boot the tenant's instance carrying a new license key. This is the
        single mechanism behind every plan change (upgrade/downgrade/lapse),
        because the plugin gate only re-reads the key at startup."""

    @abstractmethod
    def restart(self, tenant: Tenant) -> None:
        """Restart the instance in place (same license)."""

    @abstractmethod
    def destroy(self, tenant: Tenant) -> None:
        """Stop + remove the instance and drop its database. Idempotent:
        destroying an already-gone tenant must not raise."""

    @abstractmethod
    def status(self, tenant: Tenant) -> InstanceStatus:
        """Report whether the instance is running and passing /healthz."""
