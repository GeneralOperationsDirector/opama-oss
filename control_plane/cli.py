"""
Manual trigger for the control plane — drive provisioning without Stripe.

The M1/M2 acceptance harness: it exercises the same domain layer
(control_plane.tenants) the Stripe webhook (M3) uses, against the local Docker
daemon, standing up a real opama container.

Usage:
    python -m control_plane.cli init
    python -m control_plane.cli provision --slug acme --email acme@example.com \
        [--tier premium] [--modules "*"] [--days 365] [--license-key <jwt>]
    python -m control_plane.cli relicense --slug acme --tier enterprise --modules "ai,grading"
    python -m control_plane.cli status   --slug acme
    python -m control_plane.cli list
    python -m control_plane.cli destroy  --slug acme

Without a signing key on disk, tenants boot in opama dev mode (all modules) so
the provisioning loop can be proven before a keypair exists.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from control_plane import tenants
from control_plane.db import engine, init_db
from control_plane.licensing import VALID_TIERS
from control_plane.models import Tenant, TenantStatus
from control_plane.provisioner.base import ProvisioningError
from control_plane.provisioner.docker import DockerProvisioner


def _get_tenant(session: Session, slug: str) -> Tenant:
    tenant = session.exec(select(Tenant).where(Tenant.slug == slug)).first()
    if not tenant:
        raise SystemExit(f"no tenant with slug '{slug}'")
    return tenant


def _period_end(days: int) -> datetime:
    return datetime.now(tz=timezone.utc) + timedelta(days=days)


def cmd_init(_args: argparse.Namespace) -> None:
    init_db()
    print("control-plane tables ready")


def cmd_provision(args: argparse.Namespace) -> None:
    provisioner = DockerProvisioner()
    with Session(engine) as session:
        existing = session.exec(select(Tenant).where(Tenant.slug == args.slug)).first()
        if existing and existing.status != TenantStatus.DESTROYED:
            raise SystemExit(f"tenant '{args.slug}' already exists (status={existing.status})")
        tenant = tenants.upsert_tenant_and_subscription(
            session,
            slug=args.slug,
            email=args.email,
            tier=args.tier,
            modules=args.modules,
            period_end=_period_end(args.days),
        )
        tenant_id = tenant.id

    try:
        url, note = tenants.apply_provision(provisioner, tenant_id, args.license_key)
    except ProvisioningError as exc:
        raise SystemExit(f"provisioning failed: {exc}")

    print(f"  license: {note}")
    print(f"provisioned '{args.slug}' → {url}")
    print(f"  license : {url}/license")
    print(f"  health  : {url}/healthz")


def cmd_relicense(args: argparse.Namespace) -> None:
    """Re-mint the tenant's license from a (possibly changed) plan and restart it
    in place — the manual stand-in for a Stripe subscription.updated event."""
    provisioner = DockerProvisioner()
    with Session(engine) as session:
        tenant = _get_tenant(session, args.slug)
        tenants.upsert_tenant_and_subscription(
            session,
            slug=tenant.slug,
            email=tenant.customer_email,
            tier=args.tier,
            modules=args.modules,
            period_end=_period_end(args.days),
        )
        tenant_id = tenant.id

    try:
        url, note = tenants.apply_relicense(provisioner, tenant_id, args.license_key)
    except ProvisioningError as exc:
        raise SystemExit(f"relicense failed: {exc}")

    print(f"  license: {note}")
    print(f"relicensed '{args.slug}' → {url}/license")


def cmd_status(args: argparse.Namespace) -> None:
    provisioner = DockerProvisioner()
    with Session(engine) as session:
        tenant = _get_tenant(session, args.slug)
        st = provisioner.status(tenant)
        print(f"{tenant.slug}: db_status={tenant.status} running={st.running} "
              f"healthy={st.healthy} detail={st.detail} url={tenant.instance_url}")


def cmd_list(_args: argparse.Namespace) -> None:
    with Session(engine) as session:
        tenants_rows = session.exec(select(Tenant)).all()
        if not tenants_rows:
            print("(no tenants)")
            return
        for t in tenants_rows:
            print(f"{t.slug:20} {t.status:12} {t.instance_url or '-'}")


def cmd_destroy(args: argparse.Namespace) -> None:
    provisioner = DockerProvisioner()
    with Session(engine) as session:
        tenant = _get_tenant(session, args.slug)
        tenant_id = tenant.id
    tenants.apply_deprovision(provisioner, tenant_id, destroy=True)
    print(f"destroyed '{args.slug}'")


def _add_plan_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--tier", default="premium", choices=sorted(VALID_TIERS))
    p.add_argument("--modules", default="*", help='"*" or e.g. "ai,grading,portfolio"')
    p.add_argument("--days", type=int, default=365, help="license validity (sets exp)")
    p.add_argument("--license-key", default="",
                   help="override: use this raw key instead of minting")


def main() -> None:
    parser = argparse.ArgumentParser(description="opama control plane (manual trigger)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create control-plane tables").set_defaults(func=cmd_init)

    p = sub.add_parser("provision", help="provision a tenant (mints a license)")
    p.add_argument("--slug", required=True)
    p.add_argument("--email", required=True)
    _add_plan_args(p)
    p.set_defaults(func=cmd_provision)

    p = sub.add_parser("relicense", help="re-mint + restart a tenant on a changed plan")
    p.add_argument("--slug", required=True)
    _add_plan_args(p)
    p.set_defaults(func=cmd_relicense)

    p = sub.add_parser("status", help="show a tenant's instance status")
    p.add_argument("--slug", required=True)
    p.set_defaults(func=cmd_status)

    sub.add_parser("list", help="list tenants").set_defaults(func=cmd_list)

    p = sub.add_parser("destroy", help="tear down a tenant")
    p.add_argument("--slug", required=True)
    p.set_defaults(func=cmd_destroy)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
