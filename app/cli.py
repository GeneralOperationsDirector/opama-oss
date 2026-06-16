"""
opama CLI — entry point for pip-installed deployments.

  opama serve    Start the API server
  opama migrate  Run database migrations (alembic upgrade head)
  opama version  Print the core version
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _ini_path() -> Path:
    """Locate alembic.ini relative to this file (works both from source and pip install)."""
    return Path(__file__).resolve().parents[1] / "alembic.ini"


def serve(args: argparse.Namespace) -> None:
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


def migrate(args: argparse.Namespace) -> None:
    ini = _ini_path()
    if not ini.exists():
        sys.exit(f"alembic.ini not found at {ini}")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ini), "upgrade", "head"],
    )
    sys.exit(result.returncode)


def version(args: argparse.Namespace) -> None:
    from app.version import CORE_VERSION
    print(f"opama {CORE_VERSION}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="opama", description="opama — Open Personal Asset Management")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    p_serve = sub.add_parser("serve", help="Start the API server")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=6000)
    p_serve.add_argument("--reload", action="store_true")
    p_serve.set_defaults(func=serve)

    p_migrate = sub.add_parser("migrate", help="Run database migrations")
    p_migrate.set_defaults(func=migrate)

    p_version = sub.add_parser("version", help="Print core version")
    p_version.set_defaults(func=version)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)
    args.func(args)


if __name__ == "__main__":
    main()
