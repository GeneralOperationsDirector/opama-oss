"""
Unit tests for services.shared.plugin_data and services.shared.user_secrets.

These exercise the additive DB-extensibility channel from
docs/MODULE_DEVELOPMENT.md §4(A): the generic `plugin_data` table and the
`user_secret` vault. Uses an in-memory SQLite engine + SQLModel — no FastAPI
app, no live API.

Run with:
    pytest tests/test_plugin_data.py --noconftest -v

(--noconftest skips tests/conftest.py's autouse fixture that requires a live
backend on localhost:8008.)
"""
import base64
import os

# Throwaway key so app.secrets doesn't try to read/write /app/config/secret_key.b64
os.environ.setdefault("OPAMA_SECRET_KEY", base64.urlsafe_b64encode(b"0" * 32).decode())

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from services.shared.models_plugin_data import PluginData
from services.shared.models_security import UserSecret
from services.shared.plugin_data import (
    get_plugin_data,
    set_plugin_data,
    clear_plugin_data,
    get_user_plugin_data,
    set_user_plugin_data,
    get_instance_plugin_data,
    set_instance_plugin_data,
)
from services.shared.user_secrets import (
    get_user_secret,
    set_user_secret,
    delete_user_secret,
    user_secret_status,
)


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(
        engine, tables=[PluginData.__table__, UserSecret.__table__]
    )
    with Session(engine) as s:
        yield s


# ---------------------------------------------------------------------------
# plugin_data
# ---------------------------------------------------------------------------

def test_get_plugin_data_missing_returns_empty_dict(session):
    assert get_plugin_data(session, "hello", "user", 1) == {}


def test_set_plugin_data_creates_row(session):
    result = set_plugin_data(session, "hello", "user", 1, greeting="hi")
    assert result == {"greeting": "hi"}
    assert get_plugin_data(session, "hello", "user", 1) == {"greeting": "hi"}


def test_set_plugin_data_merges_without_clobbering(session):
    set_plugin_data(session, "hello", "user", 1, greeting="hi")
    result = set_plugin_data(session, "hello", "user", 1, color="blue")
    assert result == {"greeting": "hi", "color": "blue"}


def test_set_plugin_data_none_deletes_key(session):
    set_plugin_data(session, "hello", "user", 1, greeting="hi", color="blue")
    result = set_plugin_data(session, "hello", "user", 1, color=None)
    assert result == {"greeting": "hi"}


def test_clear_plugin_data_removes_row(session):
    set_plugin_data(session, "hello", "user", 1, greeting="hi")
    clear_plugin_data(session, "hello", "user", 1)
    assert get_plugin_data(session, "hello", "user", 1) == {}


def test_user_and_instance_scopes_are_independent(session):
    set_user_plugin_data(session, "hello", 1, greeting="hi-user")
    set_instance_plugin_data(session, "hello", greeting="hi-instance")

    assert get_user_plugin_data(session, "hello", 1) == {"greeting": "hi-user"}
    assert get_instance_plugin_data(session, "hello") == {"greeting": "hi-instance"}


def test_different_users_are_independent(session):
    set_user_plugin_data(session, "hello", 1, greeting="hi-1")
    set_user_plugin_data(session, "hello", 2, greeting="hi-2")

    assert get_user_plugin_data(session, "hello", 1) == {"greeting": "hi-1"}
    assert get_user_plugin_data(session, "hello", 2) == {"greeting": "hi-2"}


def test_unique_constraint_on_scope(session):
    set_plugin_data(session, "hello", "user", 1, greeting="hi")
    set_plugin_data(session, "hello", "user", 1, greeting="updated")

    rows = session.exec(
        select(PluginData).where(
            PluginData.plugin_id == "hello",
            PluginData.entity_type == "user",
            PluginData.entity_id == 1,
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].data == {"greeting": "updated"}


# ---------------------------------------------------------------------------
# user_secrets
# ---------------------------------------------------------------------------

def test_get_user_secret_missing_returns_none(session):
    assert get_user_secret(session, 1, "shopify_access_token") is None


def test_user_secret_status_unset(session):
    is_set, hint = user_secret_status(session, 1, "shopify_access_token")
    assert is_set is False
    assert hint is None


def test_set_and_get_user_secret_roundtrip(session):
    set_user_secret(session, 1, "shopify_access_token", "shpat_supersecret123")
    assert get_user_secret(session, 1, "shopify_access_token") == "shpat_supersecret123"


def test_user_secret_status_after_set(session):
    set_user_secret(session, 1, "shopify_access_token", "shpat_supersecret123")
    is_set, hint = user_secret_status(session, 1, "shopify_access_token")
    assert is_set is True
    assert hint == "…t123"


def test_set_user_secret_overwrites(session):
    set_user_secret(session, 1, "shopify_access_token", "first_value")
    set_user_secret(session, 1, "shopify_access_token", "second_value")
    assert get_user_secret(session, 1, "shopify_access_token") == "second_value"


def test_delete_user_secret(session):
    set_user_secret(session, 1, "shopify_access_token", "shpat_supersecret123")
    delete_user_secret(session, 1, "shopify_access_token")
    assert get_user_secret(session, 1, "shopify_access_token") is None
    is_set, hint = user_secret_status(session, 1, "shopify_access_token")
    assert is_set is False


def test_user_secrets_scoped_per_user_and_service(session):
    set_user_secret(session, 1, "shopify_access_token", "user1-shopify")
    set_user_secret(session, 1, "openai_api_key", "user1-openai")
    set_user_secret(session, 2, "shopify_access_token", "user2-shopify")

    assert get_user_secret(session, 1, "shopify_access_token") == "user1-shopify"
    assert get_user_secret(session, 1, "openai_api_key") == "user1-openai"
    assert get_user_secret(session, 2, "shopify_access_token") == "user2-shopify"
