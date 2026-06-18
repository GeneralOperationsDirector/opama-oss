"""
Unit tests for services/shared/storage.py (pluggable upload storage).

Fully offline. LocalStorage uses a tmp dir; S3Storage is exercised with a fake
boto3 client injected via sys.modules (no AWS, no botocore required).

Run with:
    pytest tests/test_storage.py -v
"""
import sys
import types

import pytest

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from services.shared.storage import (
    LocalStorage,
    S3Storage,
    Storage,
    build_storage,
    PUBLIC_PREFIX,
)


# ---------------------------------------------------------------------------
# Key / path helpers
# ---------------------------------------------------------------------------

def test_public_path_and_key_roundtrip():
    s = LocalStorage("/tmp")
    assert s.public_path("assets/1.jpg") == f"{PUBLIC_PREFIX}/assets/1.jpg"
    assert Storage.key_from_public_path("/uploads/assets/1.jpg") == "assets/1.jpg"
    # already a bare key — unchanged
    assert Storage.key_from_public_path("assets/1.jpg") == "assets/1.jpg"


# ---------------------------------------------------------------------------
# LocalStorage
# ---------------------------------------------------------------------------

def test_local_roundtrip(tmp_path):
    s = LocalStorage(tmp_path)
    s.save("assets/1.jpg", b"hello", "image/jpeg")
    assert (tmp_path / "assets" / "1.jpg").read_bytes() == b"hello"
    assert s.read("assets/1.jpg") == b"hello"
    assert s.exists("assets/1.jpg") is True
    assert s.url("assets/1.jpg") == "/uploads/assets/1.jpg"
    assert s.remote is False
    s.delete("assets/1.jpg")
    assert s.exists("assets/1.jpg") is False
    assert s.read("assets/1.jpg") is None
    # deleting a missing key is a no-op
    s.delete("assets/nope.jpg")


# ---------------------------------------------------------------------------
# build_storage factory
# ---------------------------------------------------------------------------

def test_build_storage_defaults_local(monkeypatch, tmp_path):
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    monkeypatch.setenv("UPLOADS_PATH", str(tmp_path))
    s = build_storage()
    assert isinstance(s, LocalStorage)
    assert s.remote is False


def test_build_storage_s3_requires_bucket(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.delenv("S3_BUCKET", raising=False)
    with pytest.raises(RuntimeError):
        build_storage()


# ---------------------------------------------------------------------------
# S3Storage (fake boto3)
# ---------------------------------------------------------------------------

class _FakeS3:
    def __init__(self):
        self.calls = {}

    def put_object(self, **kw):
        self.calls["put"] = kw

    def get_object(self, **kw):
        self.calls["get"] = kw
        return {"Body": types.SimpleNamespace(read=lambda: b"data")}

    def delete_object(self, **kw):
        self.calls["del"] = kw

    def head_object(self, **kw):
        self.calls["head"] = kw

    def generate_presigned_url(self, op, Params, ExpiresIn):
        return f"https://signed/{Params['Key']}?ttl={ExpiresIn}"


def _install_fake_boto3(monkeypatch):
    client = _FakeS3()
    fake = types.ModuleType("boto3")
    fake.client = lambda *a, **k: client
    monkeypatch.setitem(sys.modules, "boto3", fake)
    return client


def test_s3_save_read_prefix_and_public_url(monkeypatch):
    client = _install_fake_boto3(monkeypatch)
    s = S3Storage("mybucket", key_prefix="media", public_base_url="https://cdn.example")
    s.save("assets/1.jpg", b"x", "image/jpeg")
    assert client.calls["put"]["Bucket"] == "mybucket"
    assert client.calls["put"]["Key"] == "media/assets/1.jpg"   # prefix applied
    assert client.calls["put"]["ContentType"] == "image/jpeg"
    assert s.read("assets/1.jpg") == b"data"
    assert s.exists("assets/1.jpg") is True
    assert s.url("assets/1.jpg") == "https://cdn.example/media/assets/1.jpg"
    assert s.remote is True


def test_s3_presigned_url_without_public_base(monkeypatch):
    _install_fake_boto3(monkeypatch)
    s = S3Storage("b")  # no public base → presigned
    assert s.url("k").startswith("https://signed/k")
