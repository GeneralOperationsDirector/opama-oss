# opama control plane

The SaaS provisioning layer that turns opama into a hosted, subscription product.
It runs as its **own process** — not an opama plugin, never loaded into a tenant
image. It holds the license **signing private key**; tenants only carry the
embedded public key (`app/license.py`) and validate offline.

> Full design + milestones: see memory `control_plane_scope` and `enterprise_hosting_plan`.
> **The license-key check in opama's plugin loader already exists** — this layer
> is the provisioning glue, not the gate.

## Architecture

```
Stripe (M3) ──▶ control_plane (FastAPI) ──▶ Provisioner ──┬─ DockerProvisioner  (local + CI)   ← M1
                       │                                   └─ FlyProvisioner     (cloud)         ← M5
                       └─ mint license (M2) ─▶ OPAMA_LICENSE_KEY injected at boot
```

A **tenant** = one opama container + one Postgres database (logical silo locally;
dedicated Postgres per tenant on Fly). The container is the *unmodified* opama
image — booting it with per-tenant `OPAMA_LICENSE_KEY` + `DATABASE_URL` is the
whole mechanism. Because opama's `plugin_loader.resolve_enabled()` reads the
license only at startup, **a plan change is a restart with a new key** —
`Provisioner.update_license()`.

## What's here

| File | Role | Milestone |
|---|---|---|
| `provisioner/base.py` | `Provisioner` ABC — the local/cloud seam | M1 |
| `provisioner/docker.py` | `DockerProvisioner` — create / update_license / restart / destroy / status | M1 |
| `provisioner/__init__.py` | `make_provisioner()` driver factory | M1 |
| `models.py` | `Tenant`, `Subscription` (control-plane DB only) | M1 |
| `config.py` | env-driven settings (control DB, tenant DB, image, ports, network, Stripe) | M1/M3 |
| `db.py` | control-plane engine + `init_db()` | M1 |
| `licensing.py` | canonical license signer (`sign_license`, `mint_for_tenant`) | M2 |
| `tenants.py` | shared domain layer (record + apply provision/relicense/deprovision) | M2/M3 |
| `cli.py` | manual trigger — the local acceptance harness | M1/M2 |
| `billing/stripe_webhook.py` | `construct_event` signature verification | M3 |
| `billing/events.py` | Stripe event → `PlanIntent` normalization (pure, unit-testable) | M3 |
| `main.py` | FastAPI app: `/billing/webhook`, `/tenants`, `/healthz` | M3 |
| `tests/e2e_docker_stripe.py` | hermetic live e2e: webhook → real tenant → premium 200→404 | M4 |

Not yet built: `provisioner/fly.py` (M5).

## End-to-end test (M4)

`tests/e2e_docker_stripe.py` proves the whole loop with **no Stripe account and no
cloud**. It self-signs Stripe webhooks with HMAC (exactly what
`stripe.Webhook.construct_event` verifies), mints the license with a throwaway RSA
keypair injected into the tenant via `OPAMA_LICENSE_PUBLIC_KEY`, provisions a real
opama container, then asserts the premium plugin is mounted — and gone again after
a cancel:

```
checkout.session.completed (tier=premium) ─▶ tenant up ─▶ /license tier=premium,
                                                          /portfolio/value != 404
customer.subscription.deleted             ─▶ re-boot   ─▶ /license tier=core,
                                                          /portfolio/value == 404
```

It is **opt-in** (never runs in the default suite). Bring the stack up first, then:

```bash
docker compose up -d --build backend   # build a *current* image (see gotcha below)
pip install -r control_plane/requirements.txt

RUN_CP_E2E=1 python -m control_plane.tests.e2e_docker_stripe   # prints progress
# or:  RUN_CP_E2E=1 pytest control_plane/tests/e2e_docker_stripe.py
```

If a precondition is missing (no Docker daemon, image, Postgres, or network — or no
postgres attached to the network) the test **skips** rather than fails. It creates a
scratch `control_plane_e2e` DB and a per-tenant DB, and tears both down (plus the
container) on exit. Override the control-plane port with `CP_E2E_PORT` if 9011 is taken.

**Gotchas the harness already guards against (all real, hit during bring-up):**

- *Rebuild the image.* The test mints with a throwaway keypair and injects the
  matching public key via `OPAMA_LICENSE_PUBLIC_KEY`. An image built before that
  override existed ignores it and rejects the license — rebuild so `/license`
  reports `tier=premium`.
- *Docker context, not just `DOCKER_HOST`.* The provisioner adopts the active
  `docker context` endpoint, so it provisions on the **same daemon as the stack**
  (Docker Desktop points the CLI at `~/.docker/desktop/docker.sock`, not
  `/var/run/docker.sock`). The precondition fails loudly if no postgres container
  sits on `opama_default` — the symptom of a daemon mismatch. Pin with
  `CONTROL_PLANE_DOCKER_HOST` if needed.
- *`docker` SDK shadowing.* The repo has a top-level `docker/` directory; from the
  repo root it shadows the docker-py package **until docker-py is actually
  installed** in site-packages (then the real package wins). On a PEP 668 box use
  `pip install --break-system-packages stripe docker`.

## Stripe webhook (M3) — local testing

```bash
# 1. Run the control plane
uvicorn control_plane.main:app --port 9000

# 2. Forward real test-mode events to it (prints a whsec_… secret — export it)
stripe listen --forward-to localhost:9000/billing/webhook
export STRIPE_WEBHOOK_SECRET=whsec_...     # restart the control plane with this

# 3. Drive it (no charges, test mode)
stripe trigger checkout.session.completed       # → provisions a tenant
stripe trigger customer.subscription.updated    # → re-mints + restarts (plan change)
stripe trigger customer.subscription.deleted    # → downgrades to core-only (or destroys)

curl localhost:9000/tenants                      # inspect what was provisioned
```

The webhook **verifies every payload** against `STRIPE_WEBHOOK_SECRET` (rejects
unsigned/forged with 400), records the tenant synchronously, then provisions in a
background task so it returns 200 within Stripe's timeout. Plan→tier/modules comes
from `STRIPE_PRICE_PLANS` (or event `metadata`, or the `DEFAULT_PLAN_*` fallback so
canned `stripe trigger` events still provision).

## Quick start (local)

```bash
pip install -r control_plane/requirements.txt

# opama image must be built and Postgres reachable (docker compose up -d once).
# Verify settings.opama_image matches your built tag (often "<project>-backend").
docker images | grep opama

# Create the control-plane DB first (its own database, default name control_plane):
#   createdb -h localhost -p 5433 -U opama_user control_plane   # or psql CREATE DATABASE

python -m control_plane.cli init
python -m control_plane.cli provision --slug acme --email acme@example.com
python -m control_plane.cli status   --slug acme
curl http://localhost:7000/license      # whatever port was assigned
python -m control_plane.cli destroy  --slug acme
```

Pass `--license-key <jwt>` (from `scripts/generate_license_key.py`) to boot a
tenant with real entitlements; omit it to boot in dev mode (all modules).

## Configuration

All via env (see `config.py` for defaults):

| Var | Purpose |
|---|---|
| `CONTROL_PLANE_DATABASE_URL` | the control plane's own DB |
| `OPAMA_IMAGE` | tenant image tag (e.g. `opama-backend:latest`) |
| `TENANT_DB_ADMIN_URL` | admin conn to CREATE/DROP tenant databases |
| `TENANT_DB_HOST` / `_PORT` / `_USER` / `_PASSWORD` | how a tenant *container* reaches Postgres over the Docker network |
| `CONTROL_PLANE_DOCKER_NETWORK` | network tenants join (must exist) |
| `TENANT_PORT_RANGE_START` / `_END` | host ports assigned to tenants |
| `TENANT_HEALTH_TIMEOUT` | seconds to wait for `/healthz` |
