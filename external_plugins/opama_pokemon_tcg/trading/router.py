# services/trading/router.py
"""
Trading API (Wish List & For-Trade)
-----------------------------------
Endpoints under /user/{user_id} to manage:
- Wish list (cards a user wants)
- Trade list (cards a user offers)

Authentication: ALL endpoints require a valid Firebase token.
Ownership: The authenticated user can only access their own wishlist/trade list.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from services.shared.database import get_session
from opama_pokemon_tcg.trading.models import WishList, TradeItem
from services.shared.models import User, Organization, ORG_ROLE_OWNER
from opama_pokemon_tcg.catalog.models import Card
from services.auth.middleware import get_current_user
from services.auth.org_context import OrgContext, get_current_org, require_org_role

router = APIRouter(prefix="/user", tags=["wish & trade"])


def _assert_owner(current_user: User, user_id: int) -> None:
    if current_user.id != user_id:
        raise HTTPException(403, "Cannot access another user's data")


# ---------------------------------------------------------------------------
# Cross-user trade matching (pool tenancy) — static routes, declared first.
# ---------------------------------------------------------------------------


class DiscoveryIn(BaseModel):
    discoverable: bool


@router.get("/discovery")
def get_discovery(ctx: OrgContext = Depends(get_current_org)):
    """Whether the active org is discoverable in the trade-matching network."""
    return {"discoverable": bool(ctx.org.trade_discoverable)}


@router.put("/discovery")
def set_discovery(
    body: DiscoveryIn,
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(require_org_role(ORG_ROLE_OWNER)),
):
    """Opt the active org in/out of trade discovery (owner only)."""
    org = session.get(Organization, ctx.org_id)
    org.trade_discoverable = bool(body.discoverable)
    session.add(org)
    session.commit()
    return {"discoverable": org.trade_discoverable}


def _card_brief(card: "Card | None", card_id: str) -> dict:
    return {
        "card_id": card_id,
        "name": card.name if card else card_id,
        "set_id": card.set_id if card else None,
        "image_small": card.image_small if card else None,
    }


@router.get("/matches")
def trade_matches(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    ctx: OrgContext = Depends(get_current_org),
):
    """Find discoverable orgs whose trade list holds cards on my wishlist (and,
    where mutual, whose wishlist holds cards I'm offering).

    Returns matches sorted mutual-first, then by overlap size. Each match lists
    `they_have` (cards I want that they offer) and `they_want` (my offered cards
    they want). Only orgs that have opted into discovery are considered.
    """
    my_org = ctx.org_id
    my_wish = set(session.exec(select(WishList.card_id).where(WishList.org_id == my_org)).all())
    my_trade = set(session.exec(select(TradeItem.card_id).where(TradeItem.org_id == my_org)).all())

    empty = {"matches": [], "my_wishlist_count": len(my_wish),
             "my_tradelist_count": len(my_trade), "discoverable_orgs": 0}
    if not my_wish and not my_trade:
        return empty

    disc_ids = [
        o for o in session.exec(
            select(Organization.id).where(
                Organization.trade_discoverable == True,  # noqa: E712
                Organization.id != my_org,
            )
        ).all()
    ]
    if not disc_ids:
        return empty

    by_org: dict[int, dict] = {}
    if my_wish:
        for oid, cid in session.exec(
            select(TradeItem.org_id, TradeItem.card_id).where(
                TradeItem.org_id.in_(disc_ids), TradeItem.card_id.in_(list(my_wish))
            )
        ).all():
            by_org.setdefault(oid, {"have": set(), "want": set()})["have"].add(cid)
    if my_trade:
        for oid, cid in session.exec(
            select(WishList.org_id, WishList.card_id).where(
                WishList.org_id.in_(disc_ids), WishList.card_id.in_(list(my_trade))
            )
        ).all():
            by_org.setdefault(oid, {"have": set(), "want": set()})["want"].add(cid)

    # Keep only orgs that offer something I want.
    by_org = {oid: v for oid, v in by_org.items() if v["have"]}
    if not by_org:
        return {**empty, "discoverable_orgs": len(disc_ids)}

    all_cids = set().union(*[v["have"] | v["want"] for v in by_org.values()])
    cards = {c.id: c for c in session.exec(select(Card).where(Card.id.in_(list(all_cids)))).all()}
    orgs = {o.id: o for o in session.exec(
        select(Organization).where(Organization.id.in_(list(by_org.keys())))).all()}

    matches = []
    for oid, v in by_org.items():
        o = orgs.get(oid)
        matches.append({
            "org_id": oid,
            "org_name": o.name if o else f"Org {oid}",
            "org_slug": o.slug if o else None,
            "mutual": bool(v["have"] and v["want"]),
            "they_have": [_card_brief(cards.get(c), c) for c in sorted(v["have"])],
            "they_want": [_card_brief(cards.get(c), c) for c in sorted(v["want"])],
        })
    matches.sort(key=lambda mm: (not mm["mutual"], -(len(mm["they_have"]) + len(mm["they_want"]))))

    return {
        "matches": matches,
        "my_wishlist_count": len(my_wish),
        "my_tradelist_count": len(my_trade),
        "discoverable_orgs": len(disc_ids),
    }


# ---------------------------------------------------------------------------
# Wish List
# ---------------------------------------------------------------------------


@router.get("/{user_id}/wishlist")
def get_wishlist(
    user_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    ctx: OrgContext = Depends(get_current_org),
):
    _assert_owner(current_user, user_id)
    q = (
        select(WishList, Card)
        .join(Card, Card.id == WishList.card_id)
        .where(WishList.org_id == ctx.org_id)
        .order_by(Card.name)
    )
    rows = session.exec(q).all()
    return [{"wishlist": wl, "card": card} for wl, card in rows]


@router.post("/{user_id}/wishlist/{card_id}")
def add_wishlist(
    user_id: int,
    card_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    ctx: OrgContext = Depends(get_current_org),
):
    _assert_owner(current_user, user_id)

    if not session.get(Card, card_id):
        raise HTTPException(status_code=404, detail=f"Card {card_id} not found")

    exists = session.exec(
        select(WishList).where(WishList.org_id == ctx.org_id, WishList.card_id == card_id)
    ).first()
    if exists:
        return {"ok": True, "id": exists.id}

    wl = WishList(org_id=ctx.org_id, user_id=user_id, card_id=card_id)
    session.add(wl)
    session.commit()
    session.refresh(wl)
    return {"ok": True, "id": wl.id}


@router.delete("/{user_id}/wishlist/{card_id}")
def remove_wishlist(
    user_id: int,
    card_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    ctx: OrgContext = Depends(get_current_org),
):
    _assert_owner(current_user, user_id)

    wl = session.exec(
        select(WishList).where(WishList.org_id == ctx.org_id, WishList.card_id == card_id)
    ).first()
    if not wl:
        raise HTTPException(status_code=404, detail="Not in wishlist")
    session.delete(wl)
    session.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Trade Items
# ---------------------------------------------------------------------------


@router.get("/{user_id}/trade")
def get_trade(
    user_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    ctx: OrgContext = Depends(get_current_org),
):
    _assert_owner(current_user, user_id)
    q = (
        select(TradeItem, Card)
        .join(Card, Card.id == TradeItem.card_id)
        .where(TradeItem.org_id == ctx.org_id)
        .order_by(Card.name)
    )
    rows = session.exec(q).all()
    return [{"trade": t, "card": card} for t, card in rows]


@router.post("/{user_id}/trade/{card_id}")
def upsert_trade(
    user_id: int,
    card_id: str,
    quantity: int = Query(1, ge=1, description="Exact quantity to set"),
    condition: str | None = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    ctx: OrgContext = Depends(get_current_org),
):
    _assert_owner(current_user, user_id)

    if not session.get(Card, card_id):
        raise HTTPException(status_code=404, detail=f"Card {card_id} not found")

    t = session.exec(
        select(TradeItem).where(
            TradeItem.org_id == ctx.org_id, TradeItem.card_id == card_id
        )
    ).first()
    if t:
        t.quantity = quantity
        t.condition = condition
    else:
        t = TradeItem(
            org_id=ctx.org_id,
            user_id=user_id,
            card_id=card_id,
            quantity=quantity,
            condition=condition,
        )
        session.add(t)

    session.commit()
    session.refresh(t)
    return {"ok": True, "id": t.id, "quantity": t.quantity}


@router.delete("/{user_id}/trade/{card_id}")
def remove_trade(
    user_id: int,
    card_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    ctx: OrgContext = Depends(get_current_org),
):
    _assert_owner(current_user, user_id)

    t = session.exec(
        select(TradeItem).where(
            TradeItem.org_id == ctx.org_id, TradeItem.card_id == card_id
        )
    ).first()
    if not t:
        raise HTTPException(status_code=404, detail="Not marked for trade")
    session.delete(t)
    session.commit()
    return {"ok": True}
