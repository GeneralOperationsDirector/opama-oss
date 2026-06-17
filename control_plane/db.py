"""
Control-plane database engine + session.

Single-file, self-contained — the control plane is intentionally decoupled from
opama's services.shared.database so it can be extracted to its own repo later.
"""
from __future__ import annotations

from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from control_plane.config import settings

# import models so SQLModel.metadata is populated before create_all()
from control_plane import models  # noqa: F401

engine = create_engine(settings.control_plane_database_url, echo=False)


def init_db() -> None:
    """Create control-plane tables. Fine for a tiny single-service DB; if this
    grows, switch to Alembic like opama core (see memory: migration_practices)."""
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
