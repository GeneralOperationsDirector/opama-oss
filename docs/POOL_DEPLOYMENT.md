# Hosted Pool Tier — Deployment Runbook

How to deploy opama as a multi-tenant **hosted SaaS (“pool”) tier**: one shared
Postgres + a stateless app fleet, with per-request entitlements, Stripe billing,
Row-Level Security tenant isolation, and object storage for uploads.

> **Design principle — everything here is inert by default.** Each subsystem is
> gated behind an env var. With none set, the app behaves exactly like the OSS /
> self-host single-box build (local-disk uploads, boot-time license gating,
> superuser DB connection, no billing). Turning the pool on is a matter of
> setting the flags below — and turning it off again is just unsetting them.

See the architecture rationale in the `pool_vs_silo` design notes. This runbook
covers only the operational steps.

---

## 0. What you are turning on

| Subsystem | Activated by | Default (off) behavior |
|---|---|---|
| Per-request entitlements (`require_tier`) | `ENTITLEMENT_MODE=org` | `license` — boot-time license gating; `require_tier` is a pass-through |
| Stripe webhook (plan flips) | `STRIPE_WEBHOOK_SECRET` | route returns 400 (unconfigured) |
| Stripe Checkout (upgrade flow) | `STRIPE_SECRET_KEY` + `STRIPE_PRICE_PLANS` | `GET /billing/config` → `{enabled:false}`; no upgrade UI |
| Object storage (S3/R2) | `STORAGE_BACKEND=s3` | `local` — disk + StaticFiles |
| RLS tenant isolation | runtime `DATABASE_URL` → non-superuser role | superuser connection bypasses RLS (policies are a no-op) |

These are independent. You can, e.g., enable object storage without billing. A
real production pool turns on **all** of them.

---

## 1. Prerequisites

- **Managed Postgres** with point-in-time recovery (Neon / Crunchy / RDS / Fly
  Managed PG). You need the **admin/owner** connection string (for migrations)
  and the ability to create a login role.
- **S3-compatible bucket** (Cloudflare R2 recommended — no egress fees) + a
  public base URL or CDN in front of it.
- **Stripe account** (start in **test mode**) with the Stripe CLI for local
  verification.
- A **domain + TLS** terminated at your reverse proxy / load balancer. The app
  speaks plain HTTP on `:8000`; never expose it without TLS.
- The app image **rebuilt** so `stripe` and `boto3` are present (both are in
  `requirements.txt`, lazily imported — a stale image predating them will 400 on
  the webhook / fail S3). `docker compose build backend` (or your registry build).

---

## 2. Environment matrix

Set these on the app fleet (and the migration job — see §3). Examples are
illustrative.

### Core / existing production knobs
```bash
DATABASE_URL=postgresql://opama_app_login:<pw>@<host>:5432/opama   # RUNTIME role (see §3)
CORS_ORIGINS=https://app.yourdomain.com
PUBLIC_API_URL=https://api.yourdomain.com    # absolute image URLs in listings
REDIS_HOST=...                               # if used
```

### Entitlements
```bash
ENTITLEMENT_MODE=org      # per-request gating from Organization.plan_*; default "license"
```

### Billing — webhook + checkout
```bash
STRIPE_SECRET_KEY=sk_live_...           # checkout session creation
STRIPE_WEBHOOK_SECRET=whsec_...         # verifies POST /billing/webhook
# price_id:tier[:modules] ; SEMICOLON-separated (modules may contain commas)
STRIPE_PRICE_PLANS="price_123:premium:*;price_456:enterprise:*"
# Optional — used when an event carries no metadata.tier and no known price
BILLING_DEFAULT_TIER=premium
BILLING_DEFAULT_MODULES=*
BILLING_DEFAULT_PERIOD_DAYS=30
# Optional — override the post-checkout return URLs (else derived from Origin)
BILLING_SUCCESS_URL=https://app.yourdomain.com/?billing=success
BILLING_CANCEL_URL=https://app.yourdomain.com/?billing=cancel
```

### Object storage (S3 / R2)
```bash
STORAGE_BACKEND=s3
S3_BUCKET=opama-media
S3_ENDPOINT_URL=https://<accountid>.r2.cloudflarestorage.com   # set for R2; omit for AWS S3
S3_REGION=auto                          # "auto" for R2; e.g. us-east-1 for S3
S3_KEY_PREFIX=prod                      # optional namespace within the bucket
S3_PUBLIC_BASE_URL=https://media.yourdomain.com   # CDN/public base; if unset → presigned GET URLs
# AWS/R2 credentials via boto3's default chain:
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

> **Removed knob:** the old global `WEBSITE_EXPORT_KEY` no longer exists. The
> storefront export endpoints now use **per-organization** keys (each owner
> generates one under Storefront → Settings → “Storefront export key”).

---

## 3. Database: migrations + the RLS connection-role flip

This is the most important and easiest-to-get-wrong step.

**The seam:** migrations create the `opama_app` role and the RLS policies — that
requires a **privileged** role (CREATE ROLE, ALTER TABLE). The **runtime** app
must connect as a **non-superuser, non-owner** login role, because Postgres
*bypasses RLS for superusers and table owners*. So migrations and runtime use
**different** roles.

The stock image boots with `alembic upgrade head && uvicorn` on a single
`DATABASE_URL`. For the pool you must **separate** these:

### 3a. Run migrations as the admin/owner role
Run once per deploy, as a job/step (not the app process):
```bash
DATABASE_URL=postgresql://<admin>:<pw>@<host>:5432/opama \
  alembic upgrade head
```
This brings the schema to head (currently **`e0f1a2b3c4d5`**) and creates:
- `opama_app` — a NOLOGIN group role with DML grants on all tables (migration
  `b6c7d8e9f0a1`),
- `org_isolation` RLS policies on the 23 org-scoped tables, keyed on the
  per-request GUC `app.current_org_id` (empty/NULL → **fails closed**, guarded
  by `NULLIF` since `e0f1a2b3c4d5`),
- the `showcase_public_read` policy (public showcases readable without a GUC,
  `c8d9e0f1a2b3`).

### 3b. Create the runtime login role (one-time)
As admin, out-of-band (never in a migration — no secrets in migrations):
```sql
CREATE ROLE opama_app_login LOGIN PASSWORD '<strong-password>' INHERIT;
GRANT opama_app TO opama_app_login;
```
Verify it does **not** bypass RLS:
```sql
SELECT rolsuper, rolbypassrls, rolinherit FROM pg_roles WHERE rolname='opama_app_login';
-- expect: f | f | t
```

### 3c. Point the app fleet at the login role
Runtime `DATABASE_URL` uses `opama_app_login` (see §2). **Disable boot-time
migrations on the app** (the login role can’t run them) — override the container
command to just `uvicorn app.main:app --host 0.0.0.0 --port 8000`, or set your
orchestrator’s migration step separately from the app step.

> RLS only *enforces* once the runtime role is the non-superuser one. Until then
> the policies are a verified no-op. The two app paths that read RLS tables
> without a user/org context are already handled in code (public showcase →
> `showcase_public_read`; storefront export → per-org key stamps the GUC), so no
> further code changes are needed before the flip.

### 3d. Per-request GUC (already wired)
`services/shared/rls.py` stamps `app.current_org_id` inside each request’s
transaction (and re-applies after mid-request commits). This happens at the
single choke point `resolve_org_context()`, covering both HTTP and MCP/tool
callers. Nothing to configure.

---

## 4. Stripe setup

1. **Products & prices** — create a recurring price per sellable tier (Premium,
   Enterprise). Copy each `price_…` id into `STRIPE_PRICE_PLANS`
   (`price:tier:modules`, `;`-separated).
2. **Webhook endpoint** — add `https://api.yourdomain.com/billing/webhook`,
   subscribe to: `checkout.session.completed`, `customer.subscription.created`,
   `customer.subscription.updated`, `customer.subscription.deleted`,
   `invoice.payment_failed`. Copy the signing secret into `STRIPE_WEBHOOK_SECRET`.
3. **Checkout** — the frontend “Upgrade” button (header `PlanBadge`, shown when
   `GET /billing/config` is enabled and the active org is below premium and the
   caller is owner) calls `POST /billing/checkout`, which creates a session with
   `client_reference_id=<org_id>` (and org_id/tier in subscription metadata).
   The webhook uses that to link the Stripe customer to the org and flip its
   `plan_tier/plan_status/current_period_end` — read per-request by
   `require_tier`.

### Local / pre-prod verification (test mode, no real charges)
```bash
stripe listen --forward-to localhost:8000/billing/webhook   # prints whsec_… → STRIPE_WEBHOOK_SECRET
stripe trigger checkout.session.completed
stripe trigger customer.subscription.deleted
```
Then assert the org’s `plan_*` flipped and a premium endpoint goes 200 → 402 on
cancel. (A real end-to-end checkout uses Stripe’s test card `4242 4242 4242 4242`.)

---

## 5. Object storage (R2 / S3)

1. Create the bucket; put a CDN / public hostname in front of it and set
   `S3_PUBLIC_BASE_URL` (preferred — stable, cacheable URLs). If you leave it
   unset, the app serves presigned GET URLs (expiring, uncacheable).
2. Set `STORAGE_BACKEND=s3` + the `S3_*` vars + credentials (§2).
3. **Migrate existing local uploads** (if any) into the bucket, preserving keys:
   ```bash
   # local files live under <UPLOADS_PATH>/{assets,grading}/...
   # upload them to s3://$S3_BUCKET/$S3_KEY_PREFIX/{assets,grading}/...
   aws s3 sync ./uploads "s3://$S3_BUCKET/$S3_KEY_PREFIX" --endpoint-url "$S3_ENDPOINT_URL"
   ```
   The DB keeps the relative `/uploads/<key>` paths; in S3 mode the app
   redirects `/uploads/<key>` (307) to the bucket/CDN URL, so no DB rewrite is
   needed.

---

## 6. Backups & resilience

- Enable **PITR** (continuous WAL archiving) on the managed Postgres + an HA
  standby with automatic failover.
- Nightly full snapshot retained N days on top of PITR.
- Offer **per-org logical export** (download-my-collection) as both a product
  feature and a user-controlled secondary backup.
- Object storage: enable bucket versioning for accidental-delete recovery.

---

## 7. Go-live verification checklist

Run after the flip, against the live stack:

- [ ] App healthy: `GET /healthz` → 200; startup logs show plugins loaded.
- [ ] **RLS enforcing:** confirm the runtime DB role is non-superuser
      (`SELECT current_user, rolbypassrls …` → `f`). A user sees only their
      org’s rows; another org’s asset id → 404.
- [ ] **Public read works under RLS:** an anonymous `GET /showcases/public/{id}`
      returns public showcases (regression guard for the empty-GUC bug fixed in
      `e0f1a2b3c4d5`).
- [ ] **Entitlements:** with `ENTITLEMENT_MODE=org`, a free org gets `402
      upgrade_required` on a premium endpoint (e.g. `/portfolio/value`); a
      premium org gets 200.
- [ ] **Billing webhook:** `stripe trigger checkout.session.completed` (or a
      real test checkout) flips the org to premium; `…subscription.deleted`
      flips it back; both return 200.
- [ ] **Checkout:** the header Upgrade button redirects to Stripe and, after a
      test payment, the `PlanBadge` clears (webhook applied).
- [ ] **Storefront export key:** owner generates a key under Storefront →
      Settings; `GET /assets/website-listings` with `X-Export-Key: <key>`
      returns only that org’s listings.
- [ ] **Object storage:** upload an asset image → it lands in the bucket; the
      image renders via the CDN URL; deleting the asset removes the object.

---

## 8. Rollback / kill-switches

Each subsystem reverts independently by unsetting its flag and redeploying:

- **Entitlements off:** unset `ENTITLEMENT_MODE` (→ `license`) — `require_tier`
  becomes a pass-through immediately; nobody is gated.
- **Billing off:** unset `STRIPE_WEBHOOK_SECRET` / `STRIPE_SECRET_KEY` — webhook
  400s, upgrade UI hides. (Existing plan rows are untouched.)
- **Storage back to disk:** set `STORAGE_BACKEND=local` (ensure the objects also
  exist on disk, or sync them back).
- **RLS off:** point runtime `DATABASE_URL` back at a superuser/BYPASSRLS role —
  policies become a no-op. (Schema unchanged; reversible.)

The `org_isolation` / `showcase_public_read` policies and the `opama_app` role
are left in place by migration downgrades intentionally (they may be granted to
a live login role); removing them is a deliberate ops action.

---

## 9. Reference — pool migration chain

| Revision | Adds |
|---|---|
| `d2e3f4a5b6c7` | `organization` + `membership` tables; org-of-one backfill per user |
| `e3f4a5b6c7d8` | `org_id` on the Pokémon-vertical tables (nullable + backfill) |
| `f4a5b6c7d8e9` | `org_id` on the general-PAM tables (nullable + backfill) |
| `a5b6c7d8e9f0` | flip `org_id` → NOT NULL on all 23 tables (purges deleted-user orphans first) |
| `b6c7d8e9f0a1` | create `opama_app` role + `org_isolation` RLS policies |
| `c8d9e0f1a2b3` | `showcase_public_read` policy (public showcases readable without a GUC) |
| `d9e0f1a2b3c4` | `organization.export_key` (per-org storefront key) |
| `e0f1a2b3c4d5` | RLS GUC `NULLIF` guard (empty-string `app.current_org_id` fails closed, not error) — **head** |
