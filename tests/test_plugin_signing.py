"""
Unit tests for app/plugin_signing.py — instance RS256 key pair and JWT signing.

These tests run on the host with only PyJWT[crypto] installed (no FastAPI needed).
They use OPAMA_INSTANCE_PRIVATE_KEY and OPAMA_INSTANCE_ID env vars to inject
a test key pair without touching the filesystem.

Run with:
    pytest tests/test_plugin_signing.py -v
"""
from __future__ import annotations

import os
import time
import uuid

import pytest

# Generate a test RSA key pair once for the session
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization


@pytest.fixture(scope="module")
def test_rsa_keypair():
    """Generate a throwaway RSA-2048 key pair for testing."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()
    pub_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return priv_pem, pub_pem


@pytest.fixture(autouse=True)
def inject_test_keys(test_rsa_keypair, monkeypatch):
    """Inject the test key pair via env vars so plugin_signing uses them."""
    priv_pem, _ = test_rsa_keypair
    test_id = str(uuid.uuid4())
    monkeypatch.setenv("OPAMA_INSTANCE_PRIVATE_KEY", priv_pem)
    monkeypatch.setenv("OPAMA_INSTANCE_ID", test_id)

    # Clear the module-level cache between tests
    import app.plugin_signing as ps
    ps._private_pem = None
    ps._public_pem = None
    ps._instance_id = None
    yield
    ps._private_pem = None
    ps._public_pem = None
    ps._instance_id = None


class TestKeyPair:

    def test_get_public_key_pem_returns_pem(self, test_rsa_keypair):
        from app.plugin_signing import get_public_key_pem
        _, expected_pub = test_rsa_keypair
        pub = get_public_key_pem()
        assert pub.startswith("-----BEGIN PUBLIC KEY-----")
        assert pub.strip() == expected_pub.strip()

    def test_get_instance_id_returns_injected_id(self, monkeypatch):
        from app.plugin_signing import get_instance_id
        test_id = os.environ["OPAMA_INSTANCE_ID"]
        assert get_instance_id() == test_id

    def test_get_instance_id_is_uuid_format(self):
        from app.plugin_signing import get_instance_id
        iid = get_instance_id()
        # Should be parseable as UUID
        parsed = uuid.UUID(iid)
        assert str(parsed) == iid


class TestSignPluginToken:

    def test_returns_jwt_string(self):
        from app.plugin_signing import sign_plugin_token
        token = sign_plugin_token(user_id="user_abc", plugin_id="my_plugin")
        assert isinstance(token, str)
        # JWTs have three dot-separated parts
        assert token.count(".") == 2

    def test_token_verifiable_with_public_key(self, test_rsa_keypair):
        import jwt
        from app.plugin_signing import sign_plugin_token
        _, pub_pem = test_rsa_keypair
        token = sign_plugin_token(user_id="uid_123", plugin_id="test_plugin")
        payload = jwt.decode(token, pub_pem, algorithms=["RS256"])
        assert payload["user_id"] == "uid_123"
        assert payload["plugin_id"] == "test_plugin"
        assert payload["iss"] == "opama"

    def test_token_contains_instance_id(self):
        import jwt
        from app.plugin_signing import sign_plugin_token, get_instance_id
        token = sign_plugin_token(user_id="u", plugin_id="p")
        payload = jwt.decode(token, options={"verify_signature": False}, algorithms=["RS256"])
        assert payload["instance_id"] == get_instance_id()

    def test_token_expires_in_60_seconds(self):
        import jwt
        from app.plugin_signing import sign_plugin_token
        before = int(time.time())
        token = sign_plugin_token(user_id="u", plugin_id="p")
        payload = jwt.decode(token, options={"verify_signature": False}, algorithms=["RS256"])
        exp = payload["exp"]
        iat = payload["iat"]
        assert 58 <= (exp - iat) <= 62, f"Expected ~60s TTL, got {exp - iat}s"
        assert iat >= before

    def test_empty_user_id_allowed(self):
        from app.plugin_signing import sign_plugin_token
        token = sign_plugin_token(user_id="", plugin_id="anonymous_plugin")
        assert token  # no exception

    def test_different_plugin_ids_produce_different_tokens(self):
        from app.plugin_signing import sign_plugin_token
        t1 = sign_plugin_token(user_id="u", plugin_id="plugin_a")
        t2 = sign_plugin_token(user_id="u", plugin_id="plugin_b")
        assert t1 != t2


class TestExtractUserId:

    def test_extracts_uid_from_firebase_token(self):
        import jwt as _jwt
        from app.plugin_signing import _extract_user_id
        # Create a fake Firebase-like token (unsigned, just for structure)
        fake_payload = {"uid": "firebase-user-123", "sub": "firebase-user-123"}
        # We can't sign it without a key, so use HS256 with a dummy secret
        fake_token = _jwt.encode(fake_payload, "secret", algorithm="HS256")
        result = _extract_user_id(f"Bearer {fake_token}")
        assert result == "firebase-user-123"

    def test_returns_empty_for_missing_header(self):
        from app.plugin_signing import _extract_user_id
        assert _extract_user_id("") == ""
        assert _extract_user_id("Basic abc") == ""

    def test_returns_empty_for_malformed_token(self):
        from app.plugin_signing import _extract_user_id
        assert _extract_user_id("Bearer not.a.jwt") == ""
