"""
System info endpoint — used by the in-app status panel.
Returns non-sensitive operational stats for the current organization's data.
"""
import platform
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select, func

from app.version import CORE_VERSION
from services.shared.database import get_session
from services.shared.models import User
from services.shared.models_security import AuditLog
from services.auth.middleware import get_current_user, require_admin
from services.auth.org_context import OrgContext, get_current_org
from services.custom_assets.models import CustomAsset

# Pokémon TCG and Card Grader are optional external plugins
# (external_plugins/opama_pokemon_tcg/, opama_grading/, see PLUGIN_PATHS) —
# not present in core-only deployments (e.g. oss-test stack).
try:
    from opama_pokemon_tcg.inventory.models import InventoryItem
    from opama_pokemon_tcg.decks.models import Deck
except ImportError:
    InventoryItem = None
    Deck = None

try:
    from opama_grading.models import CardGradeResult
except ImportError:
    CardGradeResult = None

router = APIRouter(prefix="/system", tags=["system"])

_START_TIME = datetime.now(timezone.utc)
_UPLOADS = Path("/app/uploads")


def _dir_size_mb(path: Path) -> float:
    if not path.exists():
        return 0.0
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return round(total / (1024 * 1024), 1)


@router.get("/info")
def system_info(
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(get_current_org),
):
    uptime_s = int((datetime.now(timezone.utc) - _START_TIME).total_seconds())
    hours, rem = divmod(uptime_s, 3600)
    minutes = rem // 60

    inventory_count = 0
    if InventoryItem is not None:
        inventory_count = session.exec(
            select(func.count()).select_from(InventoryItem)
            .where(InventoryItem.org_id == ctx.org_id)
        ).one()

    deck_count = 0
    if Deck is not None:
        deck_count = session.exec(
            select(func.count()).select_from(Deck)
            .where(Deck.org_id == ctx.org_id)
        ).one()

    asset_count = session.exec(
        select(func.count()).select_from(CustomAsset)
        .where(CustomAsset.org_id == ctx.org_id)
    ).one()

    grading_count = 0
    if CardGradeResult is not None:
        grading_count = session.exec(
            select(func.count()).select_from(CardGradeResult)
            .where(CardGradeResult.org_id == ctx.org_id)
        ).one()

    return {
        "uptime": f"{hours}h {minutes}m",
        "api_version": CORE_VERSION,
        "python": platform.python_version(),
        "uploads_mb": _dir_size_mb(_UPLOADS),
        "your_data": {
            "inventory_items": inventory_count,
            "decks": deck_count,
            "collection_items": asset_count,
            "grading_results": grading_count,
        },
    }


@router.get("/audit")
def list_audit_log(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    _: User = Depends(require_admin),
):
    """Admin-only: append-only trail of privileged actions (plugin installs, secret/settings changes, publishes)."""
    rows = session.exec(
        select(AuditLog).order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
    ).all()

    user_ids = {r.user_id for r in rows if r.user_id is not None}
    emails = {}
    if user_ids:
        for u in session.exec(select(User).where(User.id.in_(user_ids))).all():
            emails[u.id] = u.email

    return {
        "total": session.exec(select(func.count()).select_from(AuditLog)).one(),
        "items": [
            {
                "id": r.id,
                "user_id": r.user_id,
                "user_email": emails.get(r.user_id) if r.user_id else None,
                "action": r.action,
                "target": r.target,
                "ip_address": r.ip_address,
                "success": r.success,
                "detail": r.detail,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
    }
