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
from sqlmodel import Session, select

from services.shared.database import get_session
from opama_pokemon_tcg.trading.models import WishList, TradeItem
from services.shared.models import User
from opama_pokemon_tcg.catalog.models import Card
from services.auth.middleware import get_current_user
from services.auth.org_context import OrgContext, get_current_org

router = APIRouter(prefix="/user", tags=["wish & trade"])


def _assert_owner(current_user: User, user_id: int) -> None:
    if current_user.id != user_id:
        raise HTTPException(403, "Cannot access another user's data")


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
