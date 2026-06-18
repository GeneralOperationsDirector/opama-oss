"""
Unit tests for services/auth/entitlements.py (per-request tier gating).

Fully offline — no Docker, no DB. The entitlement logic only reads attributes
off an Organization-shaped object, so a SimpleNamespace stands in for the model.

Run with:
    pytest tests/test_entitlements.py -v
"""
import sys
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

import pytest

# Make sure project root is on the path
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

from services.auth.entitlements import (
    org_entitlement_error,
    assert_entitled,
    entitlement_mode,
    ENTITLEMENT_MODE_ENV,
)


def _org(tier="premium", status="active", modules="*", period_end=None):
    return SimpleNamespace(
        plan_tier=tier,
        plan_status=status,
        plan_modules=modules,
        current_period_end=period_end,
    )


# ---------------------------------------------------------------------------
# Pure logic: org_entitlement_error
# ---------------------------------------------------------------------------

def test_active_premium_org_covers_premium():
    assert org_entitlement_error(_org(tier="premium"), "premium") is None


def test_free_org_blocked_from_premium():
    err = org_entitlement_error(_org(tier="free"), "premium")
    assert err and "premium" in err


def test_enterprise_covers_premium_requirement():
    assert org_entitlement_error(_org(tier="enterprise"), "premium") is None


def test_unknown_tier_fails_closed():
    assert org_entitlement_error(_org(tier="banana"), "premium") is not None


@pytest.mark.parametrize("status", ["past_due", "canceled", "unpaid", "incomplete", ""])
def test_inactive_status_blocks_regardless_of_tier(status):
    err = org_entitlement_error(_org(tier="enterprise", status=status), "premium")
    assert err and "subscription" in err


def test_trialing_status_is_allowed():
    assert org_entitlement_error(_org(tier="premium", status="trialing"), "premium") is None


def test_expired_period_end_blocks_even_when_active():
    past = datetime.now(timezone.utc) - timedelta(days=1)
    err = org_entitlement_error(_org(tier="premium", period_end=past), "premium")
    assert err and "period" in err


def test_naive_period_end_in_future_is_allowed():
    # DB datetimes are naive UTC — must be treated as UTC, not rejected.
    future_naive = datetime.utcnow() + timedelta(days=10)
    assert org_entitlement_error(_org(tier="premium", period_end=future_naive), "premium") is None


def test_module_allow_list_permits_listed_module():
    org = _org(tier="premium", modules="portfolio,grading")
    assert org_entitlement_error(org, "premium", module="portfolio") is None


def test_module_allow_list_rejects_unlisted_module():
    org = _org(tier="premium", modules="portfolio,grading")
    err = org_entitlement_error(org, "premium", module="shopify")
    assert err and "shopify" in err


def test_wildcard_modules_allow_any():
    assert org_entitlement_error(_org(modules="*"), "premium", module="anything") is None


def test_empty_modules_allow_any():
    assert org_entitlement_error(_org(modules=""), "premium", module="anything") is None


# ---------------------------------------------------------------------------
# Mode switch: assert_entitled
# ---------------------------------------------------------------------------

def test_default_mode_is_license(monkeypatch):
    monkeypatch.delenv(ENTITLEMENT_MODE_ENV, raising=False)
    assert entitlement_mode() == "license"


def test_license_mode_is_passthrough(monkeypatch):
    # Even a free / canceled org must NOT be blocked in the default mode.
    monkeypatch.delenv(ENTITLEMENT_MODE_ENV, raising=False)
    assert_entitled(_org(tier="free", status="canceled"), "premium", module="portfolio")


def test_org_mode_allows_entitled(monkeypatch):
    monkeypatch.setenv(ENTITLEMENT_MODE_ENV, "org")
    assert_entitled(_org(tier="premium"), "premium", module="portfolio")


def test_org_mode_raises_402_for_shortfall(monkeypatch):
    monkeypatch.setenv(ENTITLEMENT_MODE_ENV, "org")
    with pytest.raises(HTTPException) as exc:
        assert_entitled(_org(tier="free"), "premium", module="portfolio")
    assert exc.value.status_code == 402
    detail = exc.value.detail
    assert detail["error"] == "upgrade_required"
    assert detail["required_tier"] == "premium"
    assert detail["current_tier"] == "free"
