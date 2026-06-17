"""
DockerProvisioner — the local + CI driver.

A tenant is one opama container plus one Postgres database. The silo is logical
locally (a database per tenant on a shared Postgres); on Fly each tenant gets its
own Postgres. Either way the container is the *unmodified* opama image — booting
it with per-tenant env (OPAMA_LICENSE_KEY, DATABASE_URL) is the whole trick. The
image already runs `alembic upgrade head` then uvicorn and exposes /healthz.

Reaching Postgres: the control plane creates the tenant database over its admin
URL (which may be localhost:5433), but the tenant *container* connects over the
shared Docker network using the service hostname (settings.tenant_db_host, e.g.
"postgres") — see config.py.

Scope note (M1): create / destroy / status / restart / update_license are real.
License *minting* is M2 — create() takes whatever key it's handed (empty == dev
mode). Stripe is M3. A routing proxy is later; M1 assigns a host port per tenant.
"""
from __future__ import annotations

import os
import socket
import subprocess
import time
from contextlib import closing

from sqlalchemy import create_engine, text

from control_plane.config import settings
from control_plane.models import Tenant
from control_plane.provisioner.base import (
    InstanceHandle,
    InstanceStatus,
    Provisioner,
    ProvisioningError,
)

try:
    import docker
    from docker.errors import APIError, NotFound
    _HAS_DOCKER = True
except ImportError:  # keep import-safe so tests/CLI can load without the SDK
    _HAS_DOCKER = False


def _resolve_docker_base_url() -> str | None:
    """Pick the Docker endpoint the provisioner should talk to.

    `docker.from_env()` only honors DOCKER_HOST — it ignores `docker context`. On a
    machine where the CLI's active context isn't the default socket (Docker Desktop
    points the CLI at ~/.docker/desktop/docker.sock while the SDK would default to
    /var/run/docker.sock), the two target *different daemons*: tenants would be
    created on a daemon that can't see the opama stack's network/Postgres and never
    go healthy. So: explicit DOCKER_HOST/config wins; otherwise adopt the CLI's
    active-context endpoint so we provision against the same daemon as the stack.
    Returns None to fall back to from_env() when neither is available.
    """
    explicit = settings.docker_host or os.getenv("DOCKER_HOST", "")
    if explicit:
        return explicit
    try:
        out = subprocess.run(
            ["docker", "context", "inspect", "--format", '{{(index .Endpoints "docker").Host}}'],
            capture_output=True, text=True, timeout=5,
        )
        host = out.stdout.strip()
        if out.returncode == 0 and host:
            return host
    except (FileNotFoundError, subprocess.SubprocessError):
        pass
    return None


def _container_name(tenant: Tenant) -> str:
    return f"opama-tenant-{tenant.slug}"


def _database_name(tenant: Tenant) -> str:
    # Postgres identifiers: keep it conservative. Slugs are already URL-safe;
    # swap any '-' for '_' so the name needs no quoting.
    return f"tenant_{tenant.slug}".replace("-", "_")


def _tenant_env(license_key: str, db_name: str) -> dict[str, str]:
    """Per-tenant environment for the opama image. Shared by create + update so
    a re-license boots with exactly the same config bar the license key."""
    env = {
        "OPAMA_LICENSE_KEY": license_key,                  # "" => dev mode
        "DATABASE_URL": settings.tenant_database_url(db_name),
        "ENABLED_PLUGINS": "",                             # empty => license-tier gating
        # External premium plugins (portfolio, grading, …) live outside services/
        # and are only *discovered* when PLUGIN_PATHS points at them — without this
        # the license tier is moot because the plugins never enter the registry.
        # Matches the opama image's own default (see docker-compose.yml / Dockerfile).
        "PLUGIN_PATHS": settings.tenant_plugin_paths,
        "REDIS_HOST": "redis",
    }
    # Only when running tenants on a custom signing keypair (see config).
    if settings.tenant_license_public_key:
        env["OPAMA_LICENSE_PUBLIC_KEY"] = settings.tenant_license_public_key
    return env


class DockerProvisioner(Provisioner):
    def __init__(self) -> None:
        if not _HAS_DOCKER:
            raise ProvisioningError(
                "docker SDK not installed — `pip install -r control_plane/requirements.txt`"
            )
        try:
            base_url = _resolve_docker_base_url()
            self._client = docker.DockerClient(base_url=base_url) if base_url else docker.from_env()
        except Exception as exc:  # noqa: BLE001 — surface any daemon connection issue uniformly
            raise ProvisioningError(f"cannot reach Docker daemon: {exc}") from exc

    # -- public API --------------------------------------------------------

    def create(self, tenant: Tenant, license_key: str) -> InstanceHandle:
        db_name = _database_name(tenant)
        self._create_database(db_name)

        port = self._allocate_port()
        name = _container_name(tenant)

        # Remove any stale container with the same name (idempotent re-create).
        self._remove_container_if_exists(name)

        try:
            container = self._client.containers.run(
                settings.opama_image,
                name=name,
                detach=True,
                network=settings.docker_network,
                ports={"8000/tcp": port},
                environment=_tenant_env(license_key, db_name),
                restart_policy={"Name": "unless-stopped"},
                labels={"opama.role": "tenant", "opama.tenant": tenant.slug},
            )
        except APIError as exc:
            raise ProvisioningError(f"failed to start tenant container: {exc}") from exc

        instance_url = f"http://localhost:{port}"
        self._wait_healthy(port)

        return InstanceHandle(
            container_id=container.id,
            host_port=port,
            instance_url=instance_url,
            database_name=db_name,
        )

    def update_license(self, tenant: Tenant, license_key: str) -> None:
        # Re-create in place: same name/port/database, new OPAMA_LICENSE_KEY.
        # The plugin gate only re-reads the key at boot, so a fresh container is
        # the entitlement-change mechanism. Reuse the recorded port to keep the
        # instance_url stable.
        if tenant.host_port is None or tenant.database_name is None:
            raise ProvisioningError(
                f"tenant '{tenant.slug}' has no recorded port/database to update"
            )
        name = _container_name(tenant)
        self._remove_container_if_exists(name)
        try:
            self._client.containers.run(
                settings.opama_image,
                name=name,
                detach=True,
                network=settings.docker_network,
                ports={"8000/tcp": tenant.host_port},
                environment=_tenant_env(license_key, tenant.database_name),
                restart_policy={"Name": "unless-stopped"},
                labels={"opama.role": "tenant", "opama.tenant": tenant.slug},
            )
        except APIError as exc:
            raise ProvisioningError(f"failed to update tenant container: {exc}") from exc
        self._wait_healthy(tenant.host_port)

    def restart(self, tenant: Tenant) -> None:
        try:
            self._client.containers.get(_container_name(tenant)).restart()
        except NotFound as exc:
            raise ProvisioningError(f"tenant '{tenant.slug}' container not found") from exc
        if tenant.host_port is not None:
            self._wait_healthy(tenant.host_port)

    def destroy(self, tenant: Tenant) -> None:
        self._remove_container_if_exists(_container_name(tenant))
        if tenant.database_name:
            self._drop_database(tenant.database_name)

    def status(self, tenant: Tenant) -> InstanceStatus:
        try:
            container = self._client.containers.get(_container_name(tenant))
        except NotFound:
            return InstanceStatus(running=False, healthy=False, detail="no container")
        running = container.status == "running"
        healthy = bool(tenant.host_port) and self._probe_health(tenant.host_port)
        return InstanceStatus(running=running, healthy=healthy, detail=container.status)

    # -- internals ---------------------------------------------------------

    def _create_database(self, db_name: str) -> None:
        # CREATE DATABASE cannot run inside a transaction block — use AUTOCOMMIT.
        admin = create_engine(settings.tenant_db_admin_url, isolation_level="AUTOCOMMIT")
        try:
            with admin.connect() as conn:
                exists = conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": db_name}
                ).scalar()
                if not exists:
                    # db_name is derived from a URL-safe slug; quote defensively anyway.
                    conn.execute(text(f'CREATE DATABASE "{db_name}"'))
        except Exception as exc:  # noqa: BLE001
            raise ProvisioningError(f"failed to create database {db_name}: {exc}") from exc
        finally:
            admin.dispose()

    def _drop_database(self, db_name: str) -> None:
        admin = create_engine(settings.tenant_db_admin_url, isolation_level="AUTOCOMMIT")
        try:
            with admin.connect() as conn:
                # Terminate stragglers so DROP doesn't block on open connections.
                conn.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = :n AND pid <> pg_backend_pid()"
                    ),
                    {"n": db_name},
                )
                conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        except Exception as exc:  # noqa: BLE001
            raise ProvisioningError(f"failed to drop database {db_name}: {exc}") from exc
        finally:
            admin.dispose()

    def _remove_container_if_exists(self, name: str) -> None:
        try:
            self._client.containers.get(name).remove(force=True)
        except NotFound:
            pass
        except APIError as exc:
            raise ProvisioningError(f"failed to remove container {name}: {exc}") from exc

    def _allocate_port(self) -> int:
        """First free TCP port in the configured range not already bound on the
        host. Good enough for local/CI; Fly assigns its own addressing."""
        for port in range(settings.port_range_start, settings.port_range_end + 1):
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
                if sock.connect_ex(("127.0.0.1", port)) != 0:  # nothing listening
                    return port
        raise ProvisioningError(
            f"no free port in range {settings.port_range_start}-{settings.port_range_end}"
        )

    def _probe_health(self, port: int) -> bool:
        import urllib.request

        try:
            with urllib.request.urlopen(f"http://localhost:{port}/healthz", timeout=2) as resp:
                return resp.status == 200
        except Exception:  # noqa: BLE001 — any failure means "not healthy yet"
            return False

    def _wait_healthy(self, port: int) -> None:
        deadline = time.monotonic() + settings.health_timeout_seconds
        while time.monotonic() < deadline:
            if self._probe_health(port):
                return
            time.sleep(2)
        raise ProvisioningError(
            f"tenant on port {port} did not become healthy within "
            f"{settings.health_timeout_seconds}s"
        )
