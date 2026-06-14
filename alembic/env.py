"""Alembic environment — wired to the app's SQLModel metadata and DATABASE_URL."""

from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

from alembic import context

# Load env files so DATABASE_URL is available when running alembic CLI
_root = Path(__file__).resolve().parents[1]
load_dotenv(_root / ".env")
load_dotenv(_root / ".env.local", override=True)

# Import ALL models so Alembic can detect schema changes via autogenerate.
from services.shared.models import User  # noqa: F401

# Every plugin's model_modules (services/*/plugin.yaml plus any PLUGIN_PATHS
# external plugins) are imported here so their tables register with
# SQLModel.metadata, regardless of which plugins ENABLED_PLUGINS activates at
# runtime — migrations manage the full schema, not just the active subset.
# This also means a relocated plugin (e.g. external_plugins/opama_<id>/) needs
# no change here: discover_plugins() finds it via PLUGIN_PATHS automatically.
from app.plugin_loader import discover_plugins, load_plugin_models  # noqa: E402

load_plugin_models(discover_plugins())

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def get_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. "
            "Copy .env.example to .env.local and set DATABASE_URL."
        )
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
