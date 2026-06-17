"""
Showcase Service - Collection Showcases
----------------------------------------------
CRUD endpoints for user showcases and showcase cards.

Similar to Decks service but for general collections/playlists. Users can
create named showcases (e.g., "Full Art Cards", "For Trade") and add any
item to them - a CustomAsset from their Collections (always available), or,
if the optional opama_pokemon_tcg plugin is installed, a Pokémon TCG catalog
card. Showcases can be public or private.

Endpoints:
- List showcases (with optional public filter)
- Create/update/delete showcases
- Add/update/remove cards from showcases
- Get public showcases for a user (profile page)
"""

from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from services.shared.database import get_session
from services.shared.models import User
from services.custom_assets.models import CustomAsset
from services.showcase.models import Showcase, ShowcaseCard
from services.auth.middleware import get_current_user, get_optional_user
from services.auth.org_context import OrgContext, get_current_org

try:
    from opama_pokemon_tcg.catalog.models import Card
except ImportError:
    Card = None

router = APIRouter()


# ---------------------------------------------------------------------------
# Card/asset resolution helpers
# ---------------------------------------------------------------------------


def _verify_card_exists(session: Session, card_id: str, ctx: OrgContext) -> None:
    """Raise 404/403 unless card_id resolves to a reference the org may add.

    CustomAsset ids are integers (stringified), so a purely numeric card_id
    is checked against the active org's collection first. Pokémon TCG catalog
    card ids are hyphenated strings (e.g. "sv9-12a") and are global/public,
    so no ownership check applies to them.
    """
    if card_id.isdigit():
        asset = session.get(CustomAsset, int(card_id))
        if asset:
            if asset.org_id != ctx.org_id:
                raise HTTPException(403, "Cannot add another organization's item to a showcase")
            return

    if Card is not None and session.get(Card, card_id):
        return

    raise HTTPException(404, f"Item {card_id} not found")


def _hydrate_card_map(session: Session, card_ids: List[str]) -> dict:
    """Batch-resolve showcase card_ids against CustomAsset and, if the
    opama_pokemon_tcg plugin is installed, the Pokémon TCG catalog.

    Returns a dict keyed by card_id with a unified shape:
    id, name, set_id, number, image_small, image_large, rarity, category,
    source ("asset" | "catalog"). Avoids N+1 queries.
    """
    result: dict = {}
    if not card_ids:
        return result

    asset_ids = [int(cid) for cid in card_ids if cid.isdigit()]
    if asset_ids:
        for a in session.exec(select(CustomAsset).where(CustomAsset.id.in_(asset_ids))).all():
            result[str(a.id)] = {
                "id": str(a.id),
                "name": a.name,
                "set_id": None,
                "number": None,
                "image_small": a.image_thumb_url or a.image_url,
                "image_large": a.image_url,
                "rarity": None,
                "category": a.category,
                "source": "asset",
            }

    remaining = [cid for cid in card_ids if cid not in result]
    if remaining and Card is not None:
        for c in session.exec(select(Card).where(Card.id.in_(remaining))).all():
            result[c.id] = {
                "id": c.id,
                "name": c.name,
                "set_id": c.set_id,
                "number": c.number,
                "image_small": c.image_small,
                "image_large": c.image_large,
                "rarity": c.rarity,
                "category": "Pokémon TCG",
                "source": "catalog",
            }

    return result


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CreateShowcaseRequest(BaseModel):
    """Request to create a new showcase."""
    title: str
    description: Optional[str] = None
    is_public: bool = False


class UpdateShowcaseRequest(BaseModel):
    """Request to update showcase metadata."""
    title: Optional[str] = None
    description: Optional[str] = None
    is_public: Optional[bool] = None


class AddCardRequest(BaseModel):
    """Request to add a card to a showcase."""
    card_id: str
    quantity: int = 1
    notes: Optional[str] = None


class UpdateCardRequest(BaseModel):
    """Request to update a card in a showcase."""
    quantity: Optional[int] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Showcase Management
# ---------------------------------------------------------------------------


@router.get("", response_model=List[dict])
def list_showcases(
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(get_current_org),
):
    """
    List showcases for the active organization, newest-first.

    Authentication: REQUIRED - returns only the active organization's showcases.
    """
    showcases = session.exec(
        select(Showcase)
        .where(Showcase.org_id == ctx.org_id)
        .order_by(Showcase.updated_at.desc())
    ).all()

    return [
        {
            "id": s.id,
            "user_id": s.user_id,
            "title": s.title,
            "description": s.description,
            "is_public": s.is_public,
            "created_at": s.created_at,
            "updated_at": s.updated_at,
        }
        for s in showcases
    ]


@router.post("", response_model=dict)
def create_showcase(
    payload: CreateShowcaseRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    ctx: OrgContext = Depends(get_current_org),
):
    """
    Create a new showcase in the active organization.

    Authentication: REQUIRED.
    """
    showcase = Showcase(
        org_id=ctx.org_id,            # owning organization (tenancy/RLS scope)
        user_id=current_user.id,      # creating/acting user (audit)
        title=payload.title,
        description=payload.description,
        is_public=payload.is_public,
    )

    session.add(showcase)
    session.commit()
    session.refresh(showcase)

    return {
        "id": showcase.id,
        "user_id": showcase.user_id,
        "title": showcase.title,
        "description": showcase.description,
        "is_public": showcase.is_public,
        "created_at": showcase.created_at,
        "updated_at": showcase.updated_at,
    }


@router.get("/{showcase_id}", response_model=dict)
def get_showcase(
    showcase_id: int,
    session: Session = Depends(get_session),
    current_user: Optional[User] = Depends(get_optional_user),
):
    """
    Get a showcase and its cards. Public showcases are visible to anyone;
    private showcases are only visible to their owner.
    """
    showcase = session.get(Showcase, showcase_id)
    if not showcase:
        raise HTTPException(404, "Showcase not found")

    if not showcase.is_public and (not current_user or current_user.id != showcase.user_id):
        raise HTTPException(403, "This showcase is private")

    # Get all cards in this showcase
    showcase_cards = session.exec(
        select(ShowcaseCard)
        .where(ShowcaseCard.showcase_id == showcase_id)
        .order_by(ShowcaseCard.added_at.desc())
    ).all()

    # Batch-hydrate cards/assets (avoid N+1 queries)
    card_ids = list({sc.card_id for sc in showcase_cards})
    cards = _hydrate_card_map(session, card_ids)

    hydrated = []
    for sc in showcase_cards:
        hydrated.append({
            "id": sc.id,
            "showcase_id": sc.showcase_id,
            "card_id": sc.card_id,
            "quantity": sc.quantity,
            "notes": sc.notes,
            "added_at": sc.added_at,
            "card": cards.get(sc.card_id),
        })

    return {
        "showcase": {
            "id": showcase.id,
            "user_id": showcase.user_id,
            "title": showcase.title,
            "description": showcase.description,
            "is_public": showcase.is_public,
            "created_at": showcase.created_at,
            "updated_at": showcase.updated_at,
        },
        "cards": hydrated
    }


@router.patch("/{showcase_id}", response_model=dict)
def update_showcase(
    showcase_id: int,
    payload: UpdateShowcaseRequest,
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(get_current_org),
):
    """
    Update showcase metadata (title, description, is_public).

    Authentication: REQUIRED - can only update the active org's showcases.
    """
    showcase = session.get(Showcase, showcase_id)
    if not showcase:
        raise HTTPException(404, "Showcase not found")

    # Verify org ownership
    if showcase.org_id != ctx.org_id:
        raise HTTPException(403, "Cannot update another organization's showcase")

    # Update fields
    if payload.title is not None:
        showcase.title = payload.title
    if payload.description is not None:
        showcase.description = payload.description
    if payload.is_public is not None:
        showcase.is_public = payload.is_public

    showcase.updated_at = datetime.utcnow()

    session.add(showcase)
    session.commit()
    session.refresh(showcase)

    return {
        "id": showcase.id,
        "user_id": showcase.user_id,
        "title": showcase.title,
        "description": showcase.description,
        "is_public": showcase.is_public,
        "created_at": showcase.created_at,
        "updated_at": showcase.updated_at,
    }


@router.delete("/{showcase_id}")
def delete_showcase(
    showcase_id: int,
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(get_current_org),
):
    """
    Delete a showcase and all its cards.

    Authentication: REQUIRED - can only delete the active org's showcases.
    """
    showcase = session.get(Showcase, showcase_id)
    if not showcase:
        raise HTTPException(404, "Showcase not found")

    # Verify org ownership
    if showcase.org_id != ctx.org_id:
        raise HTTPException(403, "Cannot delete another organization's showcase")

    # Delete all showcase cards first
    showcase_cards = session.exec(
        select(ShowcaseCard).where(ShowcaseCard.showcase_id == showcase_id)
    ).all()
    for sc in showcase_cards:
        session.delete(sc)

    # Delete the showcase
    session.delete(showcase)
    session.commit()

    return {"ok": True, "id": showcase_id}


# ---------------------------------------------------------------------------
# Showcase Cards
# ---------------------------------------------------------------------------


@router.post("/{showcase_id}/cards", response_model=dict)
def add_showcase_card(
    showcase_id: int,
    payload: AddCardRequest,
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(get_current_org),
):
    """
    Add a card to a showcase (idempotent add).

    Authentication: REQUIRED - can only add cards to own showcases.

    Behavior:
    - If (showcase_id, card_id) exists → increment quantity
    - Optionally sets/updates notes

    Payload:
      - card_id (str, required)
      - quantity (int, optional; defaults to 1)
      - notes (str, optional)
    """
    showcase = session.get(Showcase, showcase_id)
    if not showcase:
        raise HTTPException(404, "Showcase not found")

    # Verify org ownership
    if showcase.org_id != ctx.org_id:
        raise HTTPException(403, "Cannot add cards to another organization's showcase")

    # Verify the referenced item exists and is accessible to this org
    _verify_card_exists(session, payload.card_id, ctx)

    # Check if card already in showcase
    existing = session.exec(
        select(ShowcaseCard).where(
            (ShowcaseCard.showcase_id == showcase_id) &
            (ShowcaseCard.card_id == payload.card_id)
        )
    ).first()

    if existing:
        # Increment quantity
        existing.quantity += max(1, payload.quantity)
        if payload.notes is not None:
            existing.notes = payload.notes
        session.add(existing)
        item_id = existing.id
    else:
        # Create new showcase card
        sc = ShowcaseCard(
            showcase_id=showcase_id,
            card_id=payload.card_id,
            quantity=max(1, payload.quantity),
            notes=payload.notes,
        )
        session.add(sc)
        session.flush()
        item_id = sc.id

    # Update showcase updated_at
    showcase.updated_at = datetime.utcnow()
    session.add(showcase)

    session.commit()

    return {"id": item_id, "merged": existing is not None}


@router.patch("/{showcase_id}/cards/{card_item_id}", response_model=dict)
def update_showcase_card(
    showcase_id: int,
    card_item_id: int,
    payload: UpdateCardRequest,
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(get_current_org),
):
    """
    Update a card's quantity or notes in a showcase.

    Authentication: REQUIRED - can only update cards in the active org's showcases.

    If quantity is set to 0 or less, the card is removed from the showcase.
    """
    showcase_card = session.get(ShowcaseCard, card_item_id)
    if not showcase_card or showcase_card.showcase_id != showcase_id:
        raise HTTPException(404, "Showcase card not found")

    # Verify showcase org ownership
    showcase = session.get(Showcase, showcase_id)
    if not showcase or showcase.org_id != ctx.org_id:
        raise HTTPException(403, "Cannot update cards in another organization's showcase")

    # Update fields
    if payload.quantity is not None:
        if payload.quantity <= 0:
            # Remove card from showcase
            session.delete(showcase_card)
            session.commit()
            return {"deleted": True, "id": card_item_id}
        else:
            showcase_card.quantity = payload.quantity

    if payload.notes is not None:
        showcase_card.notes = payload.notes

    session.add(showcase_card)

    # Update showcase updated_at
    showcase = session.get(Showcase, showcase_id)
    if showcase:
        showcase.updated_at = datetime.utcnow()
        session.add(showcase)

    session.commit()
    session.refresh(showcase_card)

    return {
        "id": showcase_card.id,
        "card_id": showcase_card.card_id,
        "quantity": showcase_card.quantity,
        "notes": showcase_card.notes,
    }


@router.delete("/{showcase_id}/cards/{card_item_id}")
def remove_showcase_card(
    showcase_id: int,
    card_item_id: int,
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(get_current_org),
):
    """
    Remove a card from a showcase.

    Authentication: REQUIRED - can only remove cards from the active org's showcases.
    """
    showcase_card = session.get(ShowcaseCard, card_item_id)
    if not showcase_card or showcase_card.showcase_id != showcase_id:
        raise HTTPException(404, "Showcase card not found")

    # Verify showcase org ownership
    showcase = session.get(Showcase, showcase_id)
    if not showcase or showcase.org_id != ctx.org_id:
        raise HTTPException(403, "Cannot remove cards from another organization's showcase")

    session.delete(showcase_card)

    # Update showcase updated_at
    showcase = session.get(Showcase, showcase_id)
    if showcase:
        showcase.updated_at = datetime.utcnow()
        session.add(showcase)

    session.commit()

    return {"ok": True, "id": card_item_id}


# ---------------------------------------------------------------------------
# Public Profile
# ---------------------------------------------------------------------------


@router.get("/public/{user_id}", response_model=List[dict])
def get_public_showcases(
    user_id: int,
    session: Session = Depends(get_session),
):
    """
    Get a user's public showcases (no auth required).

    Returns showcases with is_public=True, ordered by updated_at desc.
    Includes hydrated card data for display.
    """
    showcases = session.exec(
        select(Showcase).where(
            (Showcase.user_id == user_id) &
            (Showcase.is_public == True)
        ).order_by(Showcase.updated_at.desc())
    ).all()

    result = []
    for showcase in showcases:
        # Get cards for this showcase
        showcase_cards = session.exec(
            select(ShowcaseCard)
            .where(ShowcaseCard.showcase_id == showcase.id)
            .order_by(ShowcaseCard.added_at.desc())
        ).all()

        # Hydrate cards/assets
        card_ids = list({sc.card_id for sc in showcase_cards})
        cards = _hydrate_card_map(session, card_ids)

        hydrated = []
        for sc in showcase_cards:
            hydrated.append({
                "id": sc.id,
                "card_id": sc.card_id,
                "quantity": sc.quantity,
                "notes": sc.notes,
                "card": cards.get(sc.card_id),
            })

        result.append({
            "showcase": {
                "id": showcase.id,
                "user_id": showcase.user_id,
                "title": showcase.title,
                "description": showcase.description,
                "is_public": showcase.is_public,
                "created_at": showcase.created_at,
                "updated_at": showcase.updated_at,
            },
            "cards": hydrated
        })

    return result
