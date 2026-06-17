"""
opama control plane — the SaaS provisioning layer.

This package is NOT an opama plugin and must never be imported into a tenant
instance. It runs as its own process (its own DB, its own Docker network) and
holds the one secret tenants never see: the license *signing* private key.
Tenant instances validate licenses offline with the embedded public key in
app/license.py.

Responsibilities (built out across milestones — see memory: control_plane_scope):
  M1  (this scaffold) — Provisioner abstraction + DockerProvisioner + Tenant model.
  M2  — mint license on create (control_plane/licensing.py).
  M3  — Stripe webhook → provisioner actions.
  M4  — local end-to-end test (stripe CLI + Docker driver).
  M5  — FlyProvisioner adapter.
"""
