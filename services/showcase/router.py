"""
Showcase Service - Card Collection Management
----------------------------------------------
CRUD endpoints for user showcases and showcase cards.

Similar to Decks service but for general card collections/playlists.
Users can create named showcases (e.g., "Full Art Cards", "For Trade")
and add any cards to them. Showcases can be public or private.

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
from opama_pokemon_tcg.catalog.models import Card
from services.showcase.models import Showcase, ShowcaseCard
from services.auth.middleware import get_current_user, get_optional_user

router = APIRouter()


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
    current_user: User = Depends(get_current_user),
):
    """
    List showcases for the authenticated user, newest-first.

    Authentication: REQUIRED - returns only the authenticated user's showcases.
    """
    target_user_id = current_user.id

    showcases = session.exec(
        select(Showcase)
        .where(Showcase.user_id == target_user_id)
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
):
    """
    Create a new showcase for the authenticated user.

    Authentication: REQUIRED.
    """
    target_user_id = current_user.id

    showcase = Showcase(
        user_id=target_user_id,
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

    # Batch-hydrate cards (avoid N+1 queries)
    card_ids = list({sc.card_id for sc in showcase_cards})
    cards = {}
    if card_ids:
        cards = {
            c.id: c for c in session.exec(select(Card).where(Card.id.in_(card_ids))).all()
        }

    hydrated = []
    for sc in showcase_cards:
        c = cards.get(sc.card_id)
        hydrated.append({
            "id": sc.id,
            "showcase_id": sc.showcase_id,
            "card_id": sc.card_id,
            "quantity": sc.quantity,
            "notes": sc.notes,
            "added_at": sc.added_at,
            "card": {
                "id": c.id,
                "name": c.name,
                "set_id": c.set_id,
                "number": c.number,
                "rarity": c.rarity,
                "image_small": c.image_small,
                "image_large": c.image_large,
            } if c else None
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
    current_user: User = Depends(get_current_user),
):
    """
    Update showcase metadata (title, description, is_public).

    Authentication: REQUIRED - can only update own showcases.
    """
    showcase = session.get(Showcase, showcase_id)
    if not showcase:
        raise HTTPException(404, "Showcase not found")

    # Verify ownership
    if showcase.user_id != current_user.id:
        raise HTTPException(403, "Cannot update another user's showcase")

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
    current_user: User = Depends(get_current_user),
):
    """
    Delete a showcase and all its cards.

    Authentication: REQUIRED - can only delete own showcases.
    """
    showcase = session.get(Showcase, showcase_id)
    if not showcase:
        raise HTTPException(404, "Showcase not found")

    # Verify ownership
    if showcase.user_id != current_user.id:
        raise HTTPException(403, "Cannot delete another user's showcase")

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
    current_user: User = Depends(get_current_user),
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

    # Verify ownership
    if showcase.user_id != current_user.id:
        raise HTTPException(403, "Cannot add cards to another user's showcase")

    # Verify card exists
    if not session.get(Card, payload.card_id):
        raise HTTPException(404, f"Card {payload.card_id} not found")

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
    current_user: User = Depends(get_current_user),
):
    """
    Update a card's quantity or notes in a showcase.

    Authentication: REQUIRED - can only update cards in own showcases.

    If quantity is set to 0 or less, the card is removed from the showcase.
    """
    showcase_card = session.get(ShowcaseCard, card_item_id)
    if not showcase_card or showcase_card.showcase_id != showcase_id:
        raise HTTPException(404, "Showcase card not found")

    # Verify showcase ownership
    showcase = session.get(Showcase, showcase_id)
    if not showcase or showcase.user_id != current_user.id:
        raise HTTPException(403, "Cannot update cards in another user's showcase")

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
    current_user: User = Depends(get_current_user),
):
    """
    Remove a card from a showcase.

    Authentication: REQUIRED - can only remove cards from own showcases.
    """
    showcase_card = session.get(ShowcaseCard, card_item_id)
    if not showcase_card or showcase_card.showcase_id != showcase_id:
        raise HTTPException(404, "Showcase card not found")

    # Verify showcase ownership
    showcase = session.get(Showcase, showcase_id)
    if not showcase or showcase.user_id != current_user.id:
        raise HTTPException(403, "Cannot remove cards from another user's showcase")

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

        # Hydrate cards
        card_ids = [sc.card_id for sc in showcase_cards]
        cards = {}
        if card_ids:
            cards = {
                c.id: c for c in session.exec(select(Card).where(Card.id.in_(card_ids))).all()
            }

        hydrated = []
        for sc in showcase_cards:
            c = cards.get(sc.card_id)
            hydrated.append({
                "id": sc.id,
                "card_id": sc.card_id,
                "quantity": sc.quantity,
                "notes": sc.notes,
                "card": {
                    "id": c.id,
                    "name": c.name,
                    "set_id": c.set_id,
                    "number": c.number,
                    "rarity": c.rarity,
                    "image_small": c.image_small,
                    "image_large": c.image_large,
                } if c else None
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
