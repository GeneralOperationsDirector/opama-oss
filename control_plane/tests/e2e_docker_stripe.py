"""
End-to-end test for the control plane (M4).

Proves the whole provisioning loop with no cloud and no Stripe account:

    self-signed Stripe webhook  ──▶  control_plane (real FastAPI subprocess)
        ──▶  DockerProvisioner spins a real opama tenant container
        ──▶  assert the *premium* plugin is mounted (license = premium)
    self-signed cancel webhook  ──▶  downgrade to core-only
        ──▶  assert the premium plugin is gone (404)

How it stays hermetic:
  * Stripe events are signed locally with HMAC against a throwaway
    STRIPE_WEBHOOK_SECRET — byte-for-byte what `stripe.Webhook.construct_event`
    verifies — so no `stripe listen` / network is needed and the customer id is
    fixed (provision + cancel target the same tenant).
  * A throwaway RSA keypair signs the license; the matching public key is injected
    into the tenant via OPAMA_LICENSE_PUBLIC_KEY (config.tenant_license_public_key
    → DockerProvisioner._tenant_env), so we never touch the real signing key or the
    key baked into app/license.py.
  * The control plane runs against its own scratch DB (control_plane_e2e) and a
    per-tenant database, both dropped on cleanup.

Probes (no auth needed — they distinguish "mounted" from "gated out"):
  * GET /license            — core plugin, always mounted; reports tier + validity.
  * GET /portfolio/value    — premium plugin; 401/403 when mounted, 404 when gated.

Run it directly (preferred — prints progress):
    RUN_CP_E2E=1 python -m control_plane.tests.e2e_docker_stripe

Or via pytest (guarded so it never runs in the default suite):
    RUN_CP_E2E=1 pytest control_plane/tests/e2e_docker_stripe.py

Preconditions (else the test SKIPS, it does not fail): docker SDK + reachable
daemon, the opama image present, Postgres reachable on the admin URL, and the
tenant Docker network present. Bring them up with `docker compose up -d` and a
built image first.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from control_plane.config import settings

# --- fixed identifiers (a stable customer => provision + cancel hit one tenant) -
CUSTOMER_ID = "cus_e2e_test"
TENANT_SLUG = "cus-e2e-test"          # == _slugify(CUSTOMER_ID); see billing/events.py
CUSTOMER_EMAIL = "e2e@opama.test"
SUBSCRIPTION_ID = "sub_e2e_test"
CONTROL_PLANE_DB = "control_plane_e2e"
STRIPE_SECRET = "whsec_e2e_test_secret"
PREMIUM_PROBE_PATH = "/portfolio/value"   # premium plugin (tier=premium, /portfolio)
CONTROL_PLANE_PORT = int(os.getenv("CP_E2E_PORT", "9011"))
CONTROL_PLANE_URL = f"http://localhost:{CONTROL_PLANE_PORT}"

REPO_ROOT = Path(__file__).resolve().parents[2]

# How long to wait for a first-boot tenant to come up (alembic + uvicorn). Must
# comfortably exceed the provisioner's own health timeout.
PROVISION_TIMEOUT = settings.health_timeout_seconds + 90
DOWNGRADE_TIMEOUT = settings.health_timeout_seconds + 90


class SkipE2E(Exception):
    """A precondition isn't met — skip rather than fail."""


# --------------------------------------------------------------------------- #
# Stripe-compatible signing (mirrors stripe.Webhook.construct_event)
# --------------------------------------------------------------------------- #

def _sign(payload: bytes, secret: str, timestamp: int | None = None) -> str:
    ts = timestamp if timestamp is not None else int(time.time())
    signed_payload = f"{ts}.".encode() + payload
    sig = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def _event_envelope(event_type: str, obj: dict) -> dict:
    return {
        "id": f"evt_e2e_{int(time.time()*1000)}",
        "object": "event",
        "type": event_type,
        "data": {"object": obj},
    }


def _checkout_completed_event() -> dict:
    # A Checkout Session object. metadata.tier drives the plan (see events.py
    # precedence #1), so we don't need a price map for the test.
    obj = {
        "object": "checkout.session",
        "customer": CUSTOMER_ID,
        "subscription": SUBSCRIPTION_ID,
        "customer_details": {"email": CUSTOMER_EMAIL},
        "metadata": {"tier": "premium", "modules": "*"},
    }
    return _event_envelope("checkout.session.completed", obj)


def _subscription_deleted_event() -> dict:
    obj = {
        "object": "subscription",
        "id": SUBSCRIPTION_ID,
        "customer": CUSTOMER_ID,
    }
    return _event_envelope("customer.subscription.deleted", obj)


def _post_webhook(event: dict) -> dict:
    payload = json.dumps(event).encode()
    sig = _sign(payload, STRIPE_SECRET)
    req = urllib.request.Request(
        f"{CONTROL_PLANE_URL}/billing/webhook",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json", "Stripe-Signature": sig},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


# --------------------------------------------------------------------------- #
# Small HTTP helpers
# --------------------------------------------------------------------------- #

def _get_json(url: str, timeout: int = 10) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _status_code(url: str, timeout: int = 5) -> int:
    """GET, returning the HTTP status (including 4xx) instead of raising."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except Exception:  # noqa: BLE001 — connection refused etc.
        return 0


# --------------------------------------------------------------------------- #
# Preconditions
# --------------------------------------------------------------------------- #

def _check_preconditions() -> None:
    try:
        import docker  # noqa: F401
    except ImportError as exc:
        raise SkipE2E("docker SDK not installed (pip install -r control_plane/requirements.txt)") from exc

    # Resolve the daemon the *provisioner* will use (active `docker context`, not
    # necessarily from_env's default socket) so these checks describe the same
    # daemon tenants are created on — see provisioner.docker._resolve_docker_base_url.
    from control_plane.provisioner.docker import _resolve_docker_base_url

    try:
        base_url = _resolve_docker_base_url()
        client = docker.DockerClient(base_url=base_url) if base_url else docker.from_env()
        client.ping()
    except Exception as exc:  # noqa: BLE001
        raise SkipE2E(f"Docker daemon not reachable: {exc}") from exc

    try:
        client.images.get(settings.opama_image)
    except Exception as exc:  # noqa: BLE001
        raise SkipE2E(
            f"opama image '{settings.opama_image}' not found — build it "
            "(docker compose build) or set OPAMA_IMAGE"
        ) from exc

    try:
        network = client.networks.get(settings.docker_network)
    except Exception as exc:  # noqa: BLE001
        raise SkipE2E(
            f"docker network '{settings.docker_network}' not found — "
            "`docker compose up -d` once, or set CONTROL_PLANE_DOCKER_NETWORK"
        ) from exc

    # Guard against the daemon-mismatch trap: a stray same-named network on the
    # wrong daemon would pass the check above but have no Postgres for tenants to
    # reach. Require the stack's Postgres to actually be on this network.
    network.reload()
    names = {c.name for c in network.containers}
    if not any("postgres" in n for n in names):
        raise SkipE2E(
            f"network '{settings.docker_network}' has no postgres container "
            f"(found {sorted(names) or 'nothing'}) — the provisioner's Docker daemon "
            "isn't the one running the opama stack (check `docker context` / DOCKER_HOST)"
        )

    # Postgres reachable on the admin URL (host:port parsed from the DSN).
    from sqlalchemy import create_engine, text

    try:
        eng = create_engine(settings.tenant_db_admin_url, isolation_level="AUTOCOMMIT")
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        eng.dispose()
    except Exception as exc:  # noqa: BLE001
        raise SkipE2E(f"Postgres not reachable at TENANT_DB_ADMIN_URL: {exc}") from exc

    if _port_in_use(CONTROL_PLANE_PORT):
        raise SkipE2E(f"control-plane port {CONTROL_PLANE_PORT} already in use (set CP_E2E_PORT)")


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) == 0


# --------------------------------------------------------------------------- #
# Scratch DB + throwaway keypair
# --------------------------------------------------------------------------- #

def _admin_engine():
    from sqlalchemy import create_engine

    return create_engine(settings.tenant_db_admin_url, isolation_level="AUTOCOMMIT")


def _create_control_db() -> None:
    from sqlalchemy import text

    eng = _admin_engine()
    try:
        with eng.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": CONTROL_PLANE_DB}
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{CONTROL_PLANE_DB}"'))
    finally:
        eng.dispose()


def _drop_database(name: str) -> None:
    from sqlalchemy import text

    eng = _admin_engine()
    try:
        with eng.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :n AND pid <> pg_backend_pid()"
                ),
                {"n": name},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
    finally:
        eng.dispose()


def _control_db_url() -> str:
    """The admin DSN with the database swapped to the scratch control DB."""
    base, _, _ = settings.tenant_db_admin_url.rpartition("/")
    return f"{base}/{CONTROL_PLANE_DB}"


def _make_keypair(workdir: Path) -> tuple[Path, str]:
    """Throwaway RSA keypair. Returns (private_key_path, public_key_pem)."""
    if shutil.which("openssl") is None:
        raise SkipE2E("openssl not on PATH — needed to mint a throwaway keypair")
    priv = workdir / "e2e_signing_key.pem"
    pub = workdir / "e2e_signing_key.pub.pem"
    subprocess.run(
        ["openssl", "genrsa", "-out", str(priv), "2048"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["openssl", "rsa", "-in", str(priv), "-pubout", "-out", str(pub)],
        check=True, capture_output=True,
    )
    return priv, pub.read_text()


# --------------------------------------------------------------------------- #
# Control-plane subprocess
# --------------------------------------------------------------------------- #

def _start_control_plane(private_key_path: Path, public_key_pem: str, log_path: Path) -> subprocess.Popen:
    env = dict(os.environ)
    env.update(
        {
            "STRIPE_WEBHOOK_SECRET": STRIPE_SECRET,
            "OPAMA_LICENSE_SIGNING_KEY": str(private_key_path),
            "OPAMA_LICENSE_PUBLIC_KEY": public_key_pem,   # forwarded to the tenant
            "CONTROL_PLANE_DATABASE_URL": _control_db_url(),
            "CONTROL_PLANE_PROVISIONER": "docker",
            "DESTROY_ON_CANCEL": "false",                 # cancel => downgrade, keep data
            # Make sure config picks up the same image/network defaults the harness checked.
            "OPAMA_IMAGE": settings.opama_image,
            "CONTROL_PLANE_DOCKER_NETWORK": settings.docker_network,
        }
    )
    log = open(log_path, "w")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "control_plane.main:app",
         "--port", str(CONTROL_PLANE_PORT), "--log-level", "info"],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    return proc


def _wait_control_plane_up(timeout: int = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _status_code(f"{CONTROL_PLANE_URL}/healthz") == 200:
            return
        time.sleep(0.5)
    raise RuntimeError("control plane did not become healthy")


# --------------------------------------------------------------------------- #
# Polling helpers
# --------------------------------------------------------------------------- #

def _tenant_record() -> dict | None:
    rows = _get_json(f"{CONTROL_PLANE_URL}/tenants")
    for row in rows:
        if row["slug"] == TENANT_SLUG:
            return row
    return None


def _wait_for_running(timeout: int) -> str:
    """Poll /tenants until the tenant is running; return its instance_url."""
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        row = _tenant_record()
        last = row
        if row:
            if row["status"] == "running" and row.get("instance_url"):
                return row["instance_url"]
            if row["status"] == "error":
                raise RuntimeError(f"tenant provisioning errored: {row.get('last_error')}")
        time.sleep(3)
    raise RuntimeError(f"tenant not running within {timeout}s (last={last})")


def _wait_for_tier(instance_url: str, expected_tier: str, timeout: int) -> dict:
    """Poll the tenant's own /license until it reports expected_tier."""
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            last = _get_json(f"{instance_url}/license", timeout=5)
            if last.get("tier") == expected_tier:
                return last
        except Exception:  # noqa: BLE001 — tenant may be mid-restart
            pass
        time.sleep(3)
    raise RuntimeError(f"tenant /license never reported tier={expected_tier} (last={last})")


# --------------------------------------------------------------------------- #
# Cleanup
# --------------------------------------------------------------------------- #

def _destroy_tenant_infra() -> None:
    """Remove the tenant container + database directly (independent of the CP)."""
    try:
        from control_plane.models import Tenant
        from control_plane.provisioner.docker import DockerProvisioner, _database_name

        fake = Tenant(slug=TENANT_SLUG, customer_email=CUSTOMER_EMAIL)
        fake.database_name = _database_name(fake)
        DockerProvisioner().destroy(fake)
    except Exception as exc:  # noqa: BLE001 — best effort
        print(f"  (tenant infra cleanup: {exc})")


def _stop_control_plane(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


# --------------------------------------------------------------------------- #
# The test
# --------------------------------------------------------------------------- #

def run_e2e() -> None:
    _check_preconditions()

    workdir = Path(tempfile.mkdtemp(prefix="cp_e2e_"))
    cp_log = workdir / "control_plane.log"
    proc: subprocess.Popen | None = None

    # Clean any residue from a prior aborted run so identifiers are free.
    _destroy_tenant_infra()
    _drop_database(CONTROL_PLANE_DB)

    try:
        print(f"• scratch dir: {workdir}")
        private_key_path, public_key_pem = _make_keypair(workdir)
        print("• minted throwaway RSA keypair")

        _create_control_db()
        print(f"• created scratch control DB: {CONTROL_PLANE_DB}")

        proc = _start_control_plane(private_key_path, public_key_pem, cp_log)
        _wait_control_plane_up()
        print(f"• control plane up on :{CONTROL_PLANE_PORT}")

        # --- provision: checkout.session.completed → premium tenant -----------
        print("• firing checkout.session.completed (tier=premium) …")
        resp = _post_webhook(_checkout_completed_event())
        assert resp.get("received") is True, resp
        assert resp.get("scheduled") == "provision", f"expected provision, got {resp}"

        print(f"• waiting for tenant to come up (≤{PROVISION_TIMEOUT}s, first boot is slow) …")
        instance_url = _wait_for_running(PROVISION_TIMEOUT)
        print(f"• tenant running at {instance_url}")

        lic = _wait_for_tier(instance_url, "premium", timeout=30)
        assert lic.get("valid") is True, f"license not valid: {lic}"
        assert lic.get("tier") == "premium", f"expected premium tier, got {lic}"
        print(f"• /license → valid, tier=premium  ✓")

        premium_code = _status_code(f"{instance_url}{PREMIUM_PROBE_PATH}")
        assert premium_code != 404, (
            f"premium endpoint {PREMIUM_PROBE_PATH} returned 404 while licensed premium "
            f"(expected it mounted → 401/403)"
        )
        assert premium_code != 0, "premium endpoint unreachable"
        print(f"• {PREMIUM_PROBE_PATH} → {premium_code} (mounted, not 404)  ✓")

        # --- cancel: subscription.deleted → downgrade to core-only -----------
        print("• firing customer.subscription.deleted (downgrade) …")
        resp = _post_webhook(_subscription_deleted_event())
        assert resp.get("received") is True, resp
        assert resp.get("scheduled") == "downgrade", f"expected downgrade, got {resp}"

        print(f"• waiting for tenant to re-boot core-only (≤{DOWNGRADE_TIMEOUT}s) …")
        lic = _wait_for_tier(instance_url, "core", timeout=DOWNGRADE_TIMEOUT)
        assert lic.get("tier") == "core", f"expected core tier after cancel, got {lic}"
        print("• /license → tier=core  ✓")

        # The premium plugin should now be gated out → 404. Allow a moment for the
        # fresh container to finish mounting routers.
        deadline = time.monotonic() + 30
        premium_code = None
        while time.monotonic() < deadline:
            premium_code = _status_code(f"{instance_url}{PREMIUM_PROBE_PATH}")
            if premium_code == 404:
                break
            time.sleep(2)
        assert premium_code == 404, (
            f"premium endpoint {PREMIUM_PROBE_PATH} still {premium_code} after downgrade "
            "(expected 404 — gated out)"
        )
        print(f"• {PREMIUM_PROBE_PATH} → 404 (gated out)  ✓")

        print("\nE2E PASS: provision→premium mounted, cancel→premium gated.")

    except Exception:
        # Surface the control-plane log to help diagnose a failure.
        if cp_log.exists():
            print("\n----- control_plane log (tail) -----")
            tail = cp_log.read_text().splitlines()[-40:]
            print("\n".join(tail))
            print("------------------------------------")
        raise
    finally:
        print("• cleaning up …")
        _stop_control_plane(proc)
        _destroy_tenant_infra()
        _drop_database(CONTROL_PLANE_DB)
        shutil.rmtree(workdir, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Entry points
# --------------------------------------------------------------------------- #

def test_e2e_docker_stripe():
    """pytest wrapper — skips unless RUN_CP_E2E=1 (keeps it out of the default suite)."""
    import pytest

    if os.getenv("RUN_CP_E2E") != "1":
        pytest.skip("control-plane e2e is opt-in; set RUN_CP_E2E=1 to run")
    try:
        run_e2e()
    except SkipE2E as exc:
        pytest.skip(str(exc))


if __name__ == "__main__":
    if os.getenv("RUN_CP_E2E") != "1":
        print("Refusing to run: set RUN_CP_E2E=1 to confirm (this starts real containers).")
        raise SystemExit(2)
    try:
        run_e2e()
    except SkipE2E as exc:
        print(f"SKIP: {exc}")
        raise SystemExit(0)
    except AssertionError as exc:
        print(f"FAIL: {exc}")
        raise SystemExit(1)
