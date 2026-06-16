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
import uuid
from datetime import datetime, timezone, timedelta

try:
    import jwt
except ImportError:
    print(
        "ERROR: PyJWT is not installed.\n"
        "Install with:  pip install 'PyJWT[crypto]'",
        file=sys.stderr,
    )
    sys.exit(1)

# RSA-2048 signing key — kept OUT of the repository so it can never leak.
# Point OPAMA_LICENSE_SIGNING_KEY at your PEM file (default: ./license_signing_key.pem).
# To create a new keypair (the matching public key goes in app/license.py):
#   openssl genrsa -out license_signing_key.pem 2048
_KEY_PATH = os.environ.get("OPAMA_LICENSE_SIGNING_KEY", "license_signing_key.pem")
try:
    with open(_KEY_PATH) as _fh:
        _PRIVATE_KEY = _fh.read()
except FileNotFoundError:
    print(
        f"ERROR: license signing key not found at {_KEY_PATH!r}.\n"
        "Set OPAMA_LICENSE_SIGNING_KEY or place license_signing_key.pem in the CWD.",
        file=sys.stderr,
    )
    sys.exit(1)

VALID_TIERS = {"core", "free", "premium", "enterprise"}


def generate_key(customer: str, tier: str, modules: str, days: int) -> str:
    now = datetime.now(tz=timezone.utc)
    modules_value: list[str] | str = (
        "*" if modules.strip() == "*"
        else [m.strip() for m in modules.split(",") if m.strip()]
    )
    payload = {
        "iss": "opama",
        "sub": customer,
        "customer": customer,
        "tier": tier,
        "modules": modules_value,
        "iat": now,
        "exp": now + timedelta(days=days),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, _PRIVATE_KEY, algorithm="RS256")


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
    main()
