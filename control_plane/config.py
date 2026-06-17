"""
Control-plane configuration — all env-driven, mirroring opama's own convention.

Two distinct database concerns, deliberately kept separate:

  * CONTROL_PLANE_DATABASE_URL — the control plane's OWN little DB (Tenant /
    Subscription rows). Nothing to do with any tenant.

  * TENANT_DB_* — how to (a) connect as admin to CREATE/DROP a per-tenant
    database, and (b) the host/port a *tenant container* uses to reach that
    Postgres from inside the Docker network. These differ: the control plane
    may reach Postgres on localhost:5433, while a tenant container reaches it
    as `postgres:5432` over the shared Docker network.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _parse_price_plans(raw: str) -> dict[str, tuple[str, str]]:
    """Parse STRIPE_PRICE_PLANS into {price_id: (tier, modules)}.

    Format: "price_abc=premium;price_def=enterprise:ai,grading"
    A bare "tier" means modules="*"; "tier:modules" sets an explicit allow-list.
    """
    out: dict[str, tuple[str, str]] = {}
    for part in raw.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        price_id, plan = part.split("=", 1)
        tier, _, modules = plan.partition(":")
        out[price_id.strip()] = (tier.strip(), modules.strip() or "*")
    return out


@dataclass(frozen=True)
class Settings:
    # The control plane's own database.
    control_plane_database_url: str = os.getenv(
        "CONTROL_PLANE_DATABASE_URL",
        "postgresql://opama_user:opama_dev_pass@localhost:5433/control_plane",
    )

    # The opama image a tenant runs. Locally this is whatever `docker compose
    # build` tagged (project-prefixed, e.g. "opama-backend"); override per env.
    opama_image: str = os.getenv("OPAMA_IMAGE", "opama-backend:latest")

    # Admin connection used by the control plane to CREATE/DROP tenant databases.
    tenant_db_admin_url: str = os.getenv(
        "TENANT_DB_ADMIN_URL",
        "postgresql://opama_user:opama_dev_pass@localhost:5433/postgres",
    )

    # How a *tenant container* reaches Postgres from inside the Docker network.
    # (Host differs from the admin URL above — see module docstring.)
    tenant_db_host: str = os.getenv("TENANT_DB_HOST", "postgres")
    tenant_db_port: int = int(os.getenv("TENANT_DB_PORT", "5432"))
    tenant_db_user: str = os.getenv("TENANT_DB_USER", "opama_user")
    tenant_db_password: str = os.getenv("TENANT_DB_PASSWORD", "opama_dev_pass")

    # Docker network the tenant container joins so it can reach Postgres/Redis
    # by service name. Must already exist (compose creates one per project).
    docker_network: str = os.getenv("CONTROL_PLANE_DOCKER_NETWORK", "opama_default")

    # Host port range assigned to tenant containers (the local analog of a
    # per-tenant subdomain — M1 assigns ports; routing proxy comes later).
    port_range_start: int = int(os.getenv("TENANT_PORT_RANGE_START", "7000"))
    port_range_end: int = int(os.getenv("TENANT_PORT_RANGE_END", "7999"))

    # Seconds to wait for a freshly started tenant to report /healthz healthy.
    # The opama image's compose healthcheck uses a 90s start_period (boot runs
    # pip install + alembic upgrade), so default generously.
    health_timeout_seconds: int = int(os.getenv("TENANT_HEALTH_TIMEOUT", "150"))

    # Where a tenant container discovers external (premium) plugin packages.
    # Mirrors the opama image's own default; only override to match a custom image
    # layout. Without it the license tier can't mount premium plugins (they're
    # never discovered) — see DockerProvisioner._tenant_env.
    tenant_plugin_paths: str = os.getenv("TENANT_PLUGIN_PATHS", "/app/external_plugins")

    # Docker endpoint the provisioner talks to. Empty = adopt the active `docker
    # context` (so we hit the same daemon as the CLI / the opama stack); set it to
    # pin a specific daemon. See DockerProvisioner._resolve_docker_base_url.
    docker_host: str = os.getenv("CONTROL_PLANE_DOCKER_HOST", "")

    # Which provisioner driver to use (docker now; fly in M5).
    provisioner_kind: str = os.getenv("CONTROL_PLANE_PROVISIONER", "docker")

    # Public key (PEM) to validate licenses inside tenant containers. Normally the
    # opama image ships the right key baked into app/license.py and this stays
    # empty. Set it to run tenants on a custom signing keypair without rebuilding
    # the image — passed through as OPAMA_LICENSE_PUBLIC_KEY (the e2e test relies
    # on this to use a throwaway keypair).
    tenant_license_public_key: str = os.getenv("OPAMA_LICENSE_PUBLIC_KEY", "")

    # --- Stripe (M3) ---
    # Webhook signing secret (`whsec_…`) from `stripe listen` or the dashboard —
    # every webhook payload is verified against it. No secret => webhook rejects.
    stripe_webhook_secret: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")

    # Map a Stripe price to a plan: {price_id: (tier, modules)}. When an event's
    # subscription carries no mapped price (e.g. `stripe trigger` canned events),
    # the defaults below apply so the local loop still provisions something.
    price_plans: dict[str, tuple[str, str]] = field(
        default_factory=lambda: _parse_price_plans(os.getenv("STRIPE_PRICE_PLANS", ""))
    )
    default_tier: str = os.getenv("DEFAULT_PLAN_TIER", "premium")
    default_modules: str = os.getenv("DEFAULT_PLAN_MODULES", "*")
    # Fallback license validity when an event carries no current_period_end.
    default_period_days: int = int(os.getenv("DEFAULT_PERIOD_DAYS", "30"))

    # On cancel / payment failure: destroy the instance (True) or downgrade it to
    # core-only and leave it running (False, default — data stays put).
    destroy_on_cancel: bool = os.getenv("DESTROY_ON_CANCEL", "false").lower() in {"1", "true", "yes"}

    def tenant_database_url(self, db_name: str) -> str:
        """DATABASE_URL injected into a tenant container (network-internal host)."""
        return (
            f"postgresql://{self.tenant_db_user}:{self.tenant_db_password}"
            f"@{self.tenant_db_host}:{self.tenant_db_port}/{db_name}"
        )


settings = Settings()
