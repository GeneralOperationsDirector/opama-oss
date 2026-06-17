#!/usr/bin/env python3
"""
Generate opama license keys (RS256 JWTs).

Usage:
    # Full-access premium license, 1 year
    python3 scripts/generate_license_key.py --customer "Blair" --tier premium --days 365

    # Enterprise license locked to specific plugins, 2 years
    python3 scripts/generate_license_key.py \\
        --customer "ACME Corp" --tier enterprise \\
        --modules "ai,grading,portfolio,storefront" --days 730

    # Developer/lifetime key
    python3 scripts/generate_license_key.py --customer "Dev" --tier enterprise --days 36500

IMPORTANT: Keep the private key in this script secret.
           Never commit this file to a public repository.
"""
import argparse
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Make the repo root importable when run standalone (`python scripts/...`), so
# the canonical signer in the control plane resolves.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from control_plane.licensing import load_private_key, sign_license
except ImportError as exc:
    print(
        f"ERROR: could not import the license signer ({exc}).\n"
        "Install deps with:  pip install 'PyJWT[crypto]'",
        file=sys.stderr,
    )
    sys.exit(1)

# Signing now lives in control_plane/licensing.py — the single source of truth for
# the license claim shape. This script is a thin CLI wrapper kept for back-compat.
# `_KEY_PATH`, `_PRIVATE_KEY`, and `generate_key` are preserved because
# tests/test_license.py imports them.
_KEY_PATH = os.environ.get("OPAMA_LICENSE_SIGNING_KEY", "license_signing_key.pem")
_PRIVATE_KEY: str | None = load_private_key()

VALID_TIERS = {"core", "free", "premium", "enterprise"}


def generate_key(customer: str, tier: str, modules: str, days: int) -> str:
    """Back-compat wrapper: mint a key that expires `days` from now."""
    expires_at = datetime.now(tz=timezone.utc) + timedelta(days=days)
    return sign_license(customer, tier, modules, expires_at)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate opama license keys")
    parser.add_argument("--customer", required=True, help="Customer name or email")
    parser.add_argument("--tier", default="premium", choices=sorted(VALID_TIERS))
    parser.add_argument(
        "--modules", default="*",
        help='Comma-separated backend plugin IDs, or "*" for tier-based access',
    )
    parser.add_argument("--days", type=int, default=365, help="Validity in days")
    args = parser.parse_args()

    key = generate_key(args.customer, args.tier, args.modules, args.days)
    exp = datetime.now(tz=timezone.utc) + timedelta(days=args.days)

    print(f"Customer  : {args.customer}")
    print(f"Tier      : {args.tier}")
    print(f"Modules   : {args.modules}")
    print(f"Expires   : {exp.strftime('%Y-%m-%d')} ({args.days} days)")
    print()
    print(key)


if __name__ == "__main__":
    if _PRIVATE_KEY is None:
        print(
            f"ERROR: license signing key not found at {_KEY_PATH!r}.\n"
            "Set OPAMA_LICENSE_SIGNING_KEY or place license_signing_key.pem in the CWD.",
            file=sys.stderr,
        )
        sys.exit(1)
    main()
