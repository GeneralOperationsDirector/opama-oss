"""
Unit tests for app/license.py and scripts/generate_license_key.py.

Tests run fully offline — no Docker, no network calls.

Run with:
    pytest tests/test_license.py -v
"""
import sys
from datetime import datetime, timezone, timedelta


# Make sure project root is on the path
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from app.license import (
    decode_license,
    get_license,
    LicenseInfo,
    TIER_RANK,
)

# Ensure the key generator is importable
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "scripts"))
from generate_license_key import generate_key

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_key(customer="Test", tier="premium", modules="*", days=365) -> str:
    return generate_key(customer, tier, modules, days)


# ---------------------------------------------------------------------------
# LicenseInfo dataclass
# ---------------------------------------------------------------------------

class TestLicenseInfo:

    def test_covers_tier_dev_mode(self):
        info = LicenseInfo(valid=False, tier="dev", modules="*")
        assert info.covers_tier("core") is True
        assert info.covers_tier("premium") is True

    def test_covers_tier_invalid_no_star(self):
        info = LicenseInfo(valid=False, tier="core", modules=[])
        assert info.covers_tier("core") is False

    def test_covers_tier_valid_premium(self):
        info = LicenseInfo(valid=True, tier="premium", modules=[])
        assert info.covers_tier("core") is True
        assert info.covers_tier("free") is True
        assert info.covers_tier("premium") is True
        assert info.covers_tier("enterprise") is False

    def test_allows_plugin_star_modules(self):
        info = LicenseInfo(valid=True, tier="premium", modules="*")
        assert info.allows_plugin("ai", "premium") is True
        assert info.allows_plugin("anything", "enterprise") is True

    def test_allows_plugin_explicit_list_core_always_ok(self):
        info = LicenseInfo(valid=True, tier="premium", modules=["grading"])
        assert info.allows_plugin("system", "core") is True
        assert info.allows_plugin("custom_assets", "core") is True

    def test_allows_plugin_explicit_list_unlisted_blocked(self):
        info = LicenseInfo(valid=True, tier="premium", modules=["grading"])
        assert info.allows_plugin("ai", "premium") is False
        assert info.allows_plugin("portfolio", "premium") is False

    def test_allows_plugin_explicit_list_listed_ok(self):
        info = LicenseInfo(valid=True, tier="premium", modules=["grading", "portfolio"])
        assert info.allows_plugin("grading", "premium") is True
        assert info.allows_plugin("portfolio", "premium") is True

    def test_allows_plugin_empty_list_blocks_premium(self):
        info = LicenseInfo(valid=True, tier="premium", modules=[])
        # empty list → nothing non-core is explicitly listed → blocked
        assert info.allows_plugin("ai", "premium") is False
        # core plugins are still allowed
        assert info.allows_plugin("system", "core") is True


# ---------------------------------------------------------------------------
# decode_license
# ---------------------------------------------------------------------------

class TestDecodeLicense:

    def test_empty_string_returns_invalid(self):
        result = decode_license("")
        assert result.valid is False

    def test_garbage_returns_invalid(self):
        result = decode_license("not-a-jwt-at-all")
        assert result.valid is False

    def test_valid_premium_star_key(self):
        raw = _make_key("Blair", "premium", "*", 365)
        info = decode_license(raw)
        assert info.valid is True
        assert info.tier == "premium"
        assert info.modules == "*"
        assert info.customer == "Blair"
        assert info.expires_at is not None

    def test_valid_key_expiry_is_future(self):
        raw = _make_key(days=365)
        info = decode_license(raw)
        assert info.valid is True
        assert info.expires_at > datetime.now(tz=timezone.utc)

    def test_valid_key_with_module_list(self):
        raw = _make_key(modules="grading,portfolio")
        info = decode_license(raw)
        assert info.valid is True
        assert info.modules == ["grading", "portfolio"]

    def test_valid_key_enterprise_tier(self):
        raw = _make_key(tier="enterprise")
        info = decode_license(raw)
        assert info.tier == "enterprise"

    def test_expired_key_returns_invalid(self):
        # days=0 produces a key that is already expired
        raw = _make_key(days=-1)
        info = decode_license(raw)
        assert info.valid is False
        assert "expired" in info.message.lower() or "invalid" in info.message.lower()

    def test_tampered_key_returns_invalid(self):
        raw = _make_key()
        # Flip a char in the payload section
        parts = raw.split(".")
        payload = list(parts[1])
        payload[5] = "X" if payload[5] != "X" else "Y"
        tampered = ".".join([parts[0], "".join(payload), parts[2]])
        info = decode_license(tampered)
        assert info.valid is False

    def test_wrong_issuer_returns_invalid(self):
        # Build a key manually with wrong issuer using the private key
        import jwt as _jwt
        from generate_license_key import _PRIVATE_KEY
        payload = {
            "iss": "not-opama",
            "sub": "test",
            "customer": "test",
            "tier": "premium",
            "modules": "*",
            "iat": datetime.now(tz=timezone.utc),
            "exp": datetime.now(tz=timezone.utc) + timedelta(days=1),
            "jti": "test-jti",
        }
        raw = _jwt.encode(payload, _PRIVATE_KEY, algorithm="RS256")
        info = decode_license(raw)
        assert info.valid is False
        assert "issuer" in info.message.lower()


# ---------------------------------------------------------------------------
# get_license (reads env var)
# ---------------------------------------------------------------------------

class TestGetLicense:

    def test_no_env_var_returns_dev_mode(self, monkeypatch):
        monkeypatch.delenv("OPAMA_LICENSE_KEY", raising=False)
        info = get_license()
        assert info.tier == "dev"
        assert info.modules == "*"
        assert info.valid is False  # valid=False is correct for dev (no real license)

    def test_dev_mode_allows_all_plugins(self, monkeypatch):
        monkeypatch.delenv("OPAMA_LICENSE_KEY", raising=False)
        info = get_license()
        assert info.allows_plugin("ai", "premium") is True
        assert info.allows_plugin("grading", "premium") is True
        assert info.allows_plugin("system", "core") is True

    def test_valid_key_via_env_var(self, monkeypatch):
        raw = _make_key("Blair", "premium", "*", 365)
        monkeypatch.setenv("OPAMA_LICENSE_KEY", raw)
        info = get_license()
        assert info.valid is True
        assert info.tier == "premium"

    def test_invalid_key_via_env_var(self, monkeypatch):
        monkeypatch.setenv("OPAMA_LICENSE_KEY", "garbage.token.value")
        info = get_license()
        assert info.valid is False


# ---------------------------------------------------------------------------
# TIER_RANK constant
# ---------------------------------------------------------------------------

class TestTierRank:

    def test_core_is_lowest(self):
        assert TIER_RANK["core"] < TIER_RANK["free"]
        assert TIER_RANK["free"] < TIER_RANK["premium"]
        assert TIER_RANK["premium"] < TIER_RANK["enterprise"]

    def test_all_four_tiers_defined(self):
        assert set(TIER_RANK.keys()) == {"core", "free", "premium", "enterprise"}
