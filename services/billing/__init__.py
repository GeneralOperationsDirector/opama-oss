"""
Pool-tier billing: the SaaS Stripe webhook that flips an Organization's
entitlement columns (plan_tier / plan_modules / plan_status /
current_period_end) read per-request by ``services.auth.entitlements``.

This is the shared-DB "pool" counterpart to the silo control plane's webhook
(which mints a per-tenant license JWT and provisions a container). Here there
is no signing key and no provisioning — a subscription change is just a row
update — so the whole package lives in the core app and is safe to ship in the
OSS edition. It is inert until ``STRIPE_WEBHOOK_SECRET`` is configured.
"""
