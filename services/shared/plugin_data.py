"""
Helper API for services.shared.models_plugin_data.PluginData.

DB-agnostic (takes a Session, no FastAPI import) so it's usable from route
handlers, offline tests, and any plugin type — including dynamic/pip
installs that can't declare their own tables. See
docs/MODULE_DEVELOPMENT.md §4(A) for the worked example.

set_plugin_data() does a read-modify-write merge: `{**existing, **patch}`.
A `None` value in patch deletes that key from the stored data — mirroring
the "leave blank to keep/clear" convention used for secrets elsewhere.

This is a low-write-volume settings mechanism. Modules with high write
frequency or that need SQL-level filtering on individual fields should use
a dedicated table instead (§4(B)).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, select

from services.shared.models_plugin_data import PluginData


def get_plugin_data(session: Session, plugin_id: str, entity_type: str, entity_id: int = 0) -> dict:
    row = session.exec(
        select(PluginData).where(
            PluginData.plugin_id == plugin_id,
            PluginData.entity_type == entity_type,
            PluginData.entity_id == entity_id,
        )
    ).first()
    return dict(row.data) if row else {}


def set_plugin_data(session: Session, plugin_id: str, entity_type: str, entity_id: int = 0, **patch) -> dict:
    row = session.exec(
        select(PluginData).where(
            PluginData.plugin_id == plugin_id,
            PluginData.entity_type == entity_type,
            PluginData.entity_id == entity_id,
        )
    ).first()

    if row is None:
        row = PluginData(plugin_id=plugin_id, entity_type=entity_type, entity_id=entity_id, data={})

    merged = dict(row.data)
    for key, value in patch.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value

    row.data = merged
    row.updated_at = datetime.now(timezone.utc)
    session.add(row)
    session.commit()
    session.refresh(row)
    return dict(row.data)


def clear_plugin_data(session: Session, plugin_id: str, entity_type: str, entity_id: int = 0) -> None:
    row = session.exec(
        select(PluginData).where(
            PluginData.plugin_id == plugin_id,
            PluginData.entity_type == entity_type,
            PluginData.entity_id == entity_id,
        )
    ).first()
    if row is not None:
        session.delete(row)
        session.commit()


# ── Convenience wrappers ──────────────────────────────────────────────────

def get_user_plugin_data(session: Session, plugin_id: str, user_id: int) -> dict:
    return get_plugin_data(session, plugin_id, "user", user_id)


def set_user_plugin_data(session: Session, plugin_id: str, user_id: int, **patch) -> dict:
    return set_plugin_data(session, plugin_id, "user", user_id, **patch)


def get_instance_plugin_data(session: Session, plugin_id: str) -> dict:
    return get_plugin_data(session, plugin_id, "instance", 0)


def set_instance_plugin_data(session: Session, plugin_id: str, **patch) -> dict:
    return set_plugin_data(session, plugin_id, "instance", 0, **patch)
