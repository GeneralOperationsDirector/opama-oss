"""
Unit tests for the pool billing webhook (services/billing).

Three layers, all offline:
  - event normalization (plan_from_event) — plain dicts, no Stripe, no DB
  - service apply (apply_plan_update) — in-memory SQLite, one Organization table
  - signature verification (construct_event) — self-signed HMAC, gated on the
    stripe SDK being importable

Run with:
    pytest tests/test_billing_webhook.py -v
"""
import sys
import json
import hmac
import time
import hashlib
from datetime import datetime, timezone, timedelta

import pytest

# Make sure project root is on the path
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from services.billing.events import plan_from_event, PlanUpdate
from services.billing.service import apply_plan_update
from services.billing import webhook as wh


# ---------------------------------------------------------------------------
# Event fixtures
# ---------------------------------------------------------------------------

def _checkout_event(tier="premium", org_id="7", customer="cus_123"):
    return {
        "type": "checkout.session.completed",
        "data": {"object": {
            "object": "checkout_session",
            "customer": customer,
            "client_reference_id": org_id,
            "subscription": "sub_1",
            "metadata": {"tier": tier, "modules": "*"},
        }},
    }


def _subscription_event(event_type, status="active", customer="cus_123",
                        price_id=None, period_end=None, metadata=None):
    obj = {
        "object": "subscription",
        "id": "sub_1",
        "customer": customer,
        "status": status,
        "metadata": metadata or {},
    }
    if price_id:
        obj["items"] = {"data": [{"price": {"id": price_id}}]}
    if period_end:
        obj["current_period_end"] = int(period_end.timestamp())
    return {"type": event_type, "data": {"object": obj}}


# ---------------------------------------------------------------------------
# plan_from_event
# ---------------------------------------------------------------------------

def test_checkout_completed_activates_premium():
    u = plan_from_event(_checkout_event(tier="premium", org_id="7"))
    assert u.status == "active"
    assert u.tier == "premium"
    assert u.org_id == 7
    assert u.stripe_customer_id == "cus_123"
    assert u.period_end is not None  # session has no period → default applied


def test_subscription_updated_passes_through_status():
    end = datetime.now(timezone.utc) + timedelta(days=20)
    u = plan_from_event(_subscription_event(
        "customer.subscription.updated", status="active",
        metadata={"tier": "enterprise"}, period_end=end))
    assert u.tier == "enterprise"
    assert u.status == "active"
    assert u.period_end.year == end.year


def test_subscription_deleted_keeps_tier_sets_canceled():
    u = plan_from_event(_subscription_event("customer.subscription.deleted"))
    assert u.status == "canceled"
    assert u.tier is None          # tier left unchanged on a lapse
    assert u.modules is None


def test_payment_failed_marks_past_due():
    u = plan_from_event({"type": "invoice.payment_failed",
                         "data": {"object": {"customer": "cus_123"}}})
    assert u.status == "past_due"
    assert u.tier is None


def test_unknown_event_ignored():
    assert plan_from_event({"type": "customer.created", "data": {"object": {}}}) is None


def test_price_plan_map_resolves_tier(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_PLANS", "price_pro:premium:portfolio,grading")
    u = plan_from_event(_subscription_event(
        "customer.subscription.created", price_id="price_pro"))
    assert u.tier == "premium"
    assert u.modules == "portfolio,grading"


def test_default_tier_when_no_metadata_or_price(monkeypatch):
    monkeypatch.delenv("STRIPE_PRICE_PLANS", raising=False)
    monkeypatch.setenv("BILLING_DEFAULT_TIER", "premium")
    u = plan_from_event(_subscription_event("customer.subscription.created"))
    assert u.tier == "premium"


# ---------------------------------------------------------------------------
# apply_plan_update (in-memory SQLite, one Organization table)
# ---------------------------------------------------------------------------

@pytest.fixture
def session():
    from sqlmodel import Session, create_engine
    from services.shared.models import Organization
    engine = create_engine("sqlite://")
    Organization.__table__.create(bind=engine)
    with Session(engine) as s:
        yield s


def _make_org(session, **kw):
    from services.shared.models import Organization
    org = Organization(name="Shop", slug="shop", **kw)
    session.add(org)
    session.commit()
    session.refresh(org)
    return org


def test_apply_links_customer_by_org_id_then_flips_plan(session):
    org = _make_org(session, plan_tier="free", plan_status="active")
    end = datetime.now(timezone.utc) + timedelta(days=30)
    res = apply_plan_update(PlanUpdate(
        stripe_customer_id="cus_new", org_id=org.id, status="active",
        tier="premium", modules="*", period_end=end), session)
    assert res.status == "updated" and res.org_id == org.id
    session.refresh(org)
    assert org.plan_tier == "premium"
    assert org.stripe_customer_id == "cus_new"   # linked on first event
    assert org.current_period_end.tzinfo is None  # stored naive UTC


def test_apply_resolves_by_customer_id_on_later_event(session):
    org = _make_org(session, plan_tier="premium", stripe_customer_id="cus_x",
                    plan_status="active")
    res = apply_plan_update(PlanUpdate(
        stripe_customer_id="cus_x", org_id=None, status="canceled"), session)
    assert res.status == "updated"
    session.refresh(org)
    assert org.plan_status == "canceled"
    assert org.plan_tier == "premium"            # tier retained through the lapse


def test_apply_unmatched_event_is_noop(session):
    res = apply_plan_update(PlanUpdate(
        stripe_customer_id="cus_ghost", org_id=None, status="active",
        tier="premium"), session)
    assert res.status == "unmatched" and res.org_id is None


# ---------------------------------------------------------------------------
# construct_event signature verification
# ---------------------------------------------------------------------------

def test_construct_event_unconfigured_raises(monkeypatch):
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    with pytest.raises(wh.WebhookError):
        wh.construct_event(b"{}", "t=1,v1=deadbeef")


def _stripe_sig(payload: bytes, secret: str, ts: int) -> str:
    signed = f"{ts}.{payload.decode()}".encode()
    v1 = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={v1}"


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("stripe") is None,
    reason="stripe SDK not installed",
)
def test_construct_event_accepts_valid_and_rejects_forged(monkeypatch):
    secret = "whsec_testsecret"
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", secret)
    # Real Stripe events carry a top-level "object": "event"; construct_event
    # reads it, so the fixture must include it.
    payload = json.dumps({"object": "event",
                          "type": "customer.subscription.deleted",
                          "data": {"object": {"customer": "cus_1"}}}).encode()
    ts = int(time.time())

    event = wh.construct_event(payload, _stripe_sig(payload, secret, ts))
    assert event["type"] == "customer.subscription.deleted"

    with pytest.raises(wh.WebhookError):
        wh.construct_event(payload, _stripe_sig(payload, "whsec_wrong", ts))
