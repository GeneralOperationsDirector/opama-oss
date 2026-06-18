"""
Card grading API router (mounted at /grading).

Thin HTTP layer over the grading pipeline: `/analyze` runs the OpenCV grade +
identification (see analyzer.py / identifier.py), `/transfer` saves a result
into inventory or a collection, and the rest serve the PNG report, accuracy
feedback, and per-provider identification stats. `/analyze` is rate-limited
(10/min) and validates upload content-type + size before writing to disk.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import Response
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlmodel import Session, select, func

from services.shared.database import get_session
from services.shared.models import User
from opama_pokemon_tcg.catalog.models import Card
from services.auth.middleware import get_current_user
from services.auth.org_context import OrgContext
from services.auth.entitlements import require_tier

_limiter = Limiter(key_func=get_remote_address)
from services.custom_assets.models import CustomAsset
from .analyzer import analyze_card_guided, generate_debug_images
from .identifier import identify_card, CardIdentification
from .models import CardGradeResult, GradeFeedback, IdentificationAttempt
from .report import generate_report

_UPLOADS = Path("/app/uploads/grading")


def _scan_path(result_id: int) -> Path:
    return _UPLOADS / f"{result_id}.jpg"


def _save_scan(result_id: int, image_bytes: bytes) -> None:
    _UPLOADS.mkdir(parents=True, exist_ok=True)
    _scan_path(result_id).write_bytes(image_bytes)
from .schemas import (
    GradeResultOut, CardIdentificationOut, CenteringOut, CornerOut, SurfaceOut, EdgeOut,
    RecenterIn, RecenterOut,
    TransferIn, TransferOut,
    FeedbackIn, FeedbackOut, FeedbackStats, DimensionAccuracy,
    ProviderStatsOut,
)

router = APIRouter(prefix="/grading", tags=["grading"])

# Grading is a premium-tier plugin (plugin.yaml). In the SaaS pool path
# (ENTITLEMENT_MODE=org) every org-scoped endpoint is gated on the active org's
# plan via this dependency; in the default "license" mode it is a pass-through
# that resolves the active org exactly like get_current_org.
require_grading = require_tier("premium", module="grading")

_MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB


def _parse_xywh(s: str) -> tuple[int, int, int, int]:
    parts = [int(v) for v in s.split(",")]
    if len(parts) != 4:
        raise ValueError("Guide must be 'x,y,w,h'")
    return tuple(parts)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _identification_out(r: CardGradeResult) -> Optional[CardIdentificationOut]:
    if not r.identified_name and not r.identified_number:
        return None
    return CardIdentificationOut(
        name=r.identified_name,
        number=r.identified_number,
        set_name=r.identified_set_name,
        catalog_card_id=r.identified_catalog_card_id,
        catalog_set_id=r.identified_catalog_set_id,
        catalog_match=bool(r.identified_catalog_card_id),
        confidence=r.identification_confidence or "low",
    )


def _result_to_out(r: CardGradeResult) -> GradeResultOut:
    return GradeResultOut(
        id=r.id,
        estimated_grade=r.estimated_grade,
        grade_label=r.grade_label,
        confidence=r.confidence,
        centering=CenteringOut(
            left_pct=r.centering_left_pct,
            right_pct=r.centering_right_pct,
            top_pct=r.centering_top_pct,
            bottom_pct=r.centering_bottom_pct,
            lr_ratio=f"{round(r.centering_left_pct)}/{round(r.centering_right_pct)}",
            tb_ratio=f"{round(r.centering_top_pct)}/{round(r.centering_bottom_pct)}",
            score=r.centering_score,
        ),
        corners=CornerOut(
            top_left=r.corner_tl,
            top_right=r.corner_tr,
            bottom_left=r.corner_bl,
            bottom_right=r.corner_br,
            score=r.corner_score,
        ),
        surface=SurfaceOut(
            texture_score=r.surface_texture_score or 0.0,
            scratch_risk=r.surface_scratch_risk,
            score=r.surface_score,
            flags=json.loads(r.notes or "[]"),
            symmetry=r.surface_symmetry or 0.0,
            th_h_mean=r.surface_th_h or 0.0,
            th_v_mean=r.surface_th_v or 0.0,
        ),
        edges=EdgeOut(
            top_std=r.edge_top_std or 0.0,
            bottom_std=r.edge_bottom_std or 0.0,
            left_std=r.edge_left_std or 0.0,
            right_std=r.edge_right_std or 0.0,
            score=r.edge_score,
        ),
        notes=json.loads(r.notes or "[]"),
        identification=_identification_out(r),
        transferred_to=r.transferred_to,
        transferred_item_id=r.transferred_item_id,
        analyzed_at=r.analyzed_at,
    )


def _catalog_lookup(identification: CardIdentification, session: Session) -> CardIdentification:
    """
    Try to match the identified card against the catalog.
    Tries name+number first, then name alone.
    Mutates the identification object in place and returns it.
    """
    name = identification.name
    number = identification.card_number  # leading-zero-stripped

    # Strategy 1: name + number (most specific)
    if name and number:
        # Try exact number and also zero-padded variants
        candidates = session.exec(
            select(Card).where(Card.name.ilike(f"%{name}%"))
        ).all()
        for card in candidates:
            card_num = (card.number or "").lstrip("0") or "0"
            if card_num == number:
                identification.catalog_card_id = card.id
                identification.catalog_set_id = card.set_id
                identification.catalog_match = True
                return identification

    # Strategy 2: name only — prefer exact match, fall back to first partial
    if name:
        candidates = session.exec(
            select(Card).where(Card.name.ilike(f"%{name}%")).limit(10)
        ).all()
        if candidates:
            exact = [c for c in candidates if c.name.lower() == name.lower()]
            best = exact[0] if exact else candidates[0]
            identification.catalog_card_id = best.id
            identification.catalog_set_id = best.set_id
            identification.catalog_match = True

    return identification


# ---------------------------------------------------------------------------
# Analyze
# ---------------------------------------------------------------------------

@router.post("/analyze", response_model=GradeResultOut, status_code=201)
@_limiter.limit("10/minute")
async def analyze(
    request: Request,
    image: UploadFile = File(..., description="Card scan (JPEG, PNG, or WebP, max 20 MB)"),
    card_id: Optional[str] = Query(None, description="Pre-link to a catalog card"),
    inventory_item_id: Optional[int] = Query(None),
    asset_id: Optional[int] = Query(None),
    guide_outer: Optional[str] = Query(None, description="Outer card boundary: 'x,y,w,h' in image pixels"),
    guide_inner: Optional[str] = Query(None, description="Inner border boundary: 'x,y,w,h' in image pixels"),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    ctx: OrgContext = Depends(require_grading),
):
    """
    Upload a card scan.  Returns both a grade estimate and card identification.

    **Optional guide rectangles** (drawn by the user before analysis):
      - `guide_outer` — outer card edge as `x,y,w,h` in the uploaded image's pixel space.
        Used to warp the card to standard size instead of auto-detecting edges.
      - `guide_inner` — inner border boundary as `x,y,w,h`.  When both guides are
        provided, centering is computed geometrically from their pixel difference —
        no colour or gradient detection required.

    **Grading** (OpenCV — deterministic, no AI):
      Centering, corner sharpness, surface texture, edge uniformity → PSA-scale score.

    **Identification** (Claude Vision — reads text, does not judge):
      Extracts the card name, number, and set printed on the card, then looks
      up the match in the local catalog.  Gracefully skipped if ANTHROPIC_API_KEY
      is not set.
    """
    if image.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(400, "Image must be JPEG, PNG, or WebP")

    raw = await image.read()
    if len(raw) > _MAX_IMAGE_BYTES:
        raise HTTPException(413, f"Image exceeds 20 MB ({len(raw) // 1024 // 1024} MB received)")

    # Parse optional guide rectangles
    outer_xywh: Optional[tuple[int, int, int, int]] = None
    inner_xywh: Optional[tuple[int, int, int, int]] = None
    try:
        if guide_outer:
            outer_xywh = _parse_xywh(guide_outer)
        if guide_inner:
            inner_xywh = _parse_xywh(guide_inner)
    except ValueError as exc:
        raise HTTPException(400, f"Invalid guide format: {exc}")

    # --- Grading (always runs) ---
    try:
        report = analyze_card_guided(raw, outer_xywh, inner_xywh)
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    # --- Identification (optional — fails gracefully) ---
    identification = identify_card(raw)
    if identification:
        identification = _catalog_lookup(identification, session)

    notes_json = json.dumps(report.notes)

    record = CardGradeResult(
        org_id=ctx.org_id,
        user_id=current_user.id,
        card_id=card_id,
        inventory_item_id=inventory_item_id,
        asset_id=asset_id,
        estimated_grade=report.estimated_grade,
        grade_label=report.grade_label,
        confidence=report.confidence,
        centering_left_pct=report.centering.left_pct,
        centering_right_pct=report.centering.right_pct,
        centering_top_pct=report.centering.top_pct,
        centering_bottom_pct=report.centering.bottom_pct,
        centering_score=report.centering.score,
        corner_tl=report.corners.top_left,
        corner_tr=report.corners.top_right,
        corner_bl=report.corners.bottom_left,
        corner_br=report.corners.bottom_right,
        corner_score=report.corners.score,
        surface_score=report.surface.score,
        surface_scratch_risk=report.surface.scratch_risk,
        surface_texture_score=report.surface.texture_score,
        edge_score=report.edges.score,
        edge_top_std=report.edges.top_std,
        edge_bottom_std=report.edges.bottom_std,
        edge_left_std=report.edges.left_std,
        edge_right_std=report.edges.right_std,
        surface_symmetry=report.surface.symmetry,
        surface_th_h=report.surface.th_h_mean,
        surface_th_v=report.surface.th_v_mean,
        notes=notes_json,
        guide_outer=guide_outer,
        guide_inner=guide_inner,
        # Identification
        identified_name=identification.name if identification else None,
        identified_number=identification.number if identification else None,
        identified_set_name=identification.set_name if identification else None,
        identified_catalog_card_id=identification.catalog_card_id if identification else None,
        identified_catalog_set_id=identification.catalog_set_id if identification else None,
        identification_confidence=identification.confidence if identification else None,
    )
    session.add(record)
    session.commit()
    session.refresh(record)

    # Persist the scan so it can be used in the report image and collection transfer
    _save_scan(record.id, raw)

    # Store one IdentificationAttempt row per provider so we can track accuracy
    if identification and identification.provider_results:
        for pr in identification.provider_results:
            session.add(IdentificationAttempt(
                grade_result_id=record.id,
                provider=pr.provider,
                extracted_name=pr.name,
                extracted_number=pr.number,
                extracted_set=pr.set_name,
            ))
        session.commit()

    id_out: Optional[CardIdentificationOut] = None
    if identification:
        id_out = CardIdentificationOut(
            name=identification.name,
            number=identification.number,
            set_name=identification.set_name,
            catalog_card_id=identification.catalog_card_id,
            catalog_set_id=identification.catalog_set_id,
            catalog_match=identification.catalog_match,
            confidence=identification.confidence,
        )

    return GradeResultOut(
        id=record.id,
        estimated_grade=report.estimated_grade,
        grade_label=report.grade_label,
        confidence=report.confidence,
        centering=CenteringOut(**report.centering.__dict__),
        corners=CornerOut(
            top_left=report.corners.top_left,
            top_right=report.corners.top_right,
            bottom_left=report.corners.bottom_left,
            bottom_right=report.corners.bottom_right,
            score=report.corners.score,
        ),
        surface=SurfaceOut(
            texture_score=report.surface.texture_score,
            scratch_risk=report.surface.scratch_risk,
            score=report.surface.score,
            flags=report.surface.flags,
            symmetry=report.surface.symmetry,
            th_h_mean=report.surface.th_h_mean,
            th_v_mean=report.surface.th_v_mean,
        ),
        edges=EdgeOut(
            top_std=report.edges.top_std,
            bottom_std=report.edges.bottom_std,
            left_std=report.edges.left_std,
            right_std=report.edges.right_std,
            score=report.edges.score,
        ),
        notes=report.notes,
        identification=id_out,
        analyzed_at=record.analyzed_at,
    )


# ---------------------------------------------------------------------------
# Transfer to collection
# ---------------------------------------------------------------------------

@router.post("/{result_id}/transfer", response_model=TransferOut, status_code=201)
def transfer(
    result_id: int,
    body: TransferIn,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    org: OrgContext = Depends(require_grading),
):
    """
    Create a collection item from a grading result.

    - **inventory**: Creates or merges an InventoryItem for a catalog card.
      Requires `card_id`.  Grade and grading company are pre-filled from the
      analysis; override with `actual_grade` / `grading_company` if the card
      has been professionally graded.

    - **asset**: Creates a CustomAsset.  Works even when no catalog match was
      found — suitable for high-value cards that warrant their own record.
    """
    grade_result = session.get(CardGradeResult, result_id)
    if not grade_result:
        raise HTTPException(404, f"Grade result {result_id} not found")
    if grade_result.org_id != org.org_id:
        raise HTTPException(403, "Cannot transfer another organization's result")
    if grade_result.transferred_to:
        raise HTTPException(409, f"Already transferred to {grade_result.transferred_to} (id={grade_result.transferred_item_id})")

    # --- Inventory path ---
    if body.destination == "inventory":
        if not body.card_id:
            raise HTTPException(400, "card_id is required when destination is 'inventory'")

        card = session.get(Card, body.card_id)
        if not card:
            raise HTTPException(404, f"Card '{body.card_id}' not found in catalog")

        # Merge-on-duplicate: same semantics as the inventory router
        from opama_pokemon_tcg.inventory.models import InventoryItem
        existing = session.exec(
            select(InventoryItem).where(
                InventoryItem.org_id == org.org_id,
                InventoryItem.card_id == body.card_id,
                InventoryItem.condition == body.condition,
                InventoryItem.grade == round(body.actual_grade or grade_result.estimated_grade),
            )
        ).first()

        grade_val = round(body.actual_grade if body.actual_grade is not None else grade_result.estimated_grade)
        company = body.grading_company or None

        if existing:
            existing.quantity += body.quantity
            item = existing
        else:
            item = InventoryItem(
                org_id=org.org_id,        # owning organization (tenancy scope)
                user_id=current_user.id,  # creating/acting user (audit)
                card_id=body.card_id,
                quantity=body.quantity,
                condition=body.condition,
                grade=grade_val,
                grading_company=company,
                purchase_price_per_card=body.purchase_price,
                notes=f"Graded via Card Grader — estimated {grade_result.estimated_grade} ({grade_result.grade_label})",
                acquired_at=datetime.utcnow(),
            )
            session.add(item)

        session.commit()
        session.refresh(item)
        item_id = item.id

    # --- Custom asset path ---
    else:
        name = (
            body.card_name
            or grade_result.identified_name
            or "Unknown Card"
        )
        number_suffix = f" #{grade_result.identified_number}" if grade_result.identified_number else ""
        grade_val = body.actual_grade or grade_result.estimated_grade
        grading_note = (
            f"{body.grading_company} {grade_val}" if body.grading_company
            else f"Est. grade {grade_val} ({grade_result.grade_label})"
        )

        # Use the stored scan as the collection item's image
        scan_url = f"/uploads/grading/{result_id}.jpg" if _scan_path(result_id).exists() else None

        asset = CustomAsset(
            org_id=org.org_id,        # owning organization (tenancy scope)
            user_id=current_user.id,  # creating/acting user (audit)
            name=f"{name}{number_suffix}",
            category="Trading Card",
            condition=body.condition,
            quantity=body.quantity,
            purchase_price=body.purchase_price,
            estimated_value=body.estimated_value,
            image_url=scan_url,
            description=(
                f"Graded via Card Grader on {grade_result.analyzed_at[:10]}. "
                f"Grade: {grading_note}. "
                f"Centering {grade_result.centering_score}/10 · "
                f"Corners {grade_result.corner_score}/10 · "
                f"Surface {grade_result.surface_score}/10 · "
                f"Edges {grade_result.edge_score}/10."
            ),
            notes=body.notes,
        )
        session.add(asset)
        session.commit()
        session.refresh(asset)
        item_id = asset.id

    # Mark grade result as transferred and set bidirectional link
    grade_result.transferred_to = body.destination
    grade_result.transferred_item_id = item_id
    if body.destination == "asset":
        grade_result.asset_id = item_id
    else:
        grade_result.inventory_item_id = item_id
    session.add(grade_result)

    # Record ground truth on all IdentificationAttempt rows for this result.
    # A correction is inferred when the user changed name/number during transfer.
    final_name   = body.card_name or grade_result.identified_name
    final_number = body.card_number or grade_result.identified_number
    final_card_id = body.card_id or grade_result.identified_catalog_card_id

    attempts = session.exec(
        select(IdentificationAttempt).where(
            IdentificationAttempt.grade_result_id == result_id
        )
    ).all()

    for attempt in attempts:
        attempt.actual_name    = final_name
        attempt.actual_number  = final_number
        attempt.actual_card_id = final_card_id
        attempt.name_correct = (
            attempt.extracted_name is not None
            and final_name is not None
            and attempt.extracted_name.lower().strip() == final_name.lower().strip()
        )
        attempt.number_correct = (
            attempt.extracted_number is not None
            and final_number is not None
            and attempt.extracted_number.strip() == final_number.strip()
        )
        session.add(attempt)

    session.commit()

    return TransferOut(
        destination=body.destination,
        item_id=item_id,
        card_id=body.card_id,
        message=(
            f"Added to Pokémon inventory (item #{item_id})"
            if body.destination == "inventory"
            else f"Created collection item #{item_id}"
        ),
    )


# ---------------------------------------------------------------------------
# Grading report image
# ---------------------------------------------------------------------------

@router.get("/{result_id}/report.png")
def grade_report_image(
    result_id: int,
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(require_grading),
):
    """
    Return a PNG grading report for the given result.
    Includes the stored card scan thumbnail, grade estimate, score bars,
    corner dot diagram, and observations — ready for listings.
    """
    result = session.get(CardGradeResult, result_id)
    if not result:
        raise HTTPException(404, f"Grade result {result_id} not found")
    if result.org_id != ctx.org_id:
        raise HTTPException(403, "Cannot access another organization's result")

    scan = _scan_path(result_id)
    scan_bytes = scan.read_bytes() if scan.exists() else None

    png = generate_report(
        grade=result.estimated_grade,
        grade_label=result.grade_label,
        card_name=result.identified_name,
        card_number=result.identified_catalog_card_id,
        centering_score=result.centering_score,
        lr_ratio=f"{round(result.centering_left_pct)}/{round(result.centering_right_pct)}",
        tb_ratio=f"{round(result.centering_top_pct)}/{round(result.centering_bottom_pct)}",
        corner_score=result.corner_score,
        corner_tl=result.corner_tl,
        corner_tr=result.corner_tr,
        corner_bl=result.corner_bl,
        corner_br=result.corner_br,
        surface_score=result.surface_score,
        scratch_risk=result.surface_scratch_risk,
        edge_score=result.edge_score,
        notes=json.loads(result.notes or "[]"),
        confidence=result.confidence,
        analyzed_at=result.analyzed_at,
        scan_bytes=scan_bytes,
    )

    card_slug = (result.identified_name or "card").lower().replace(" ", "-")
    filename  = f"grade-report-{card_slug}-{result_id}.png"

    return Response(
        content=png,
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Debug diagnostic images
# ---------------------------------------------------------------------------

_DEBUG_VIEWS = {"boundary", "rectified", "centering", "corners", "surface", "edges", "grade"}


@router.get("/{result_id}/debug/{view}")
def grade_debug_image(
    result_id: int,
    view: str,
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(require_grading),
):
    """
    Return a diagnostic PNG for a single grading dimension.

    **view** must be one of: ``rectified`` | ``centering`` | ``corners`` | ``surface`` | ``edges``

    - **rectified** — perspective-corrected card (verify boundary detection worked)
    - **centering** — detected inner border lines + sampling bands overlaid on the card
    - **corners** — 2×2 grid: original patch (left) vs Sobel gradient heatmap (right)
    - **surface** — inner artwork region with horizontal and vertical top-hat results
    - **edges** — edge strips highlighted with standard-deviation labels
    """
    if view not in _DEBUG_VIEWS:
        raise HTTPException(400, f"view must be one of: {', '.join(sorted(_DEBUG_VIEWS))}")

    result = session.get(CardGradeResult, result_id)
    if not result:
        raise HTTPException(404, f"Grade result {result_id} not found")
    if result.org_id != ctx.org_id:
        raise HTTPException(403, "Cannot access another organization's result")

    scan = _scan_path(result_id)
    if not scan.exists():
        raise HTTPException(404, "Original scan not available for this result")

    outer_guide = _parse_xywh(result.guide_outer) if result.guide_outer else None
    inner_guide = _parse_xywh(result.guide_inner) if result.guide_inner else None
    try:
        debug_images = generate_debug_images(scan.read_bytes(), outer_guide, inner_guide)
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    return Response(
        content=debug_images[view],
        media_type="image/png",
        headers={"Content-Disposition": f'inline; filename="debug-{view}-{result_id}.png"'},
    )


# ---------------------------------------------------------------------------
# Color-hint re-centering
# ---------------------------------------------------------------------------

@router.post("/{result_id}/recenter", response_model=RecenterOut)
def recenter_with_color(
    result_id: int,
    body: RecenterIn,
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(require_grading),
):
    """
    Re-run the centering measurement using a border colour sampled by the user.

    The caller supplies an RGB colour sampled from the card's printed border
    (e.g. the yellow band on a base-set card).  The backend builds an HSV mask
    for that hue, finds where the coloured band begins on each of the four sides,
    and uses those positions as the inner-border distances — replacing the
    gradient-based estimate with a colour-based one.

    The new centering score and overall grade are persisted to the database and
    returned so the UI can update in-place without a page reload.
    """
    from .analyzer import measure_centering_color_hint, _rectify, _compute_grade
    import cv2
    import numpy as np

    result = session.get(CardGradeResult, result_id)
    if not result:
        raise HTTPException(404, f"Grade result {result_id} not found")
    if result.org_id != ctx.org_id:
        raise HTTPException(403, "Cannot access another organization's result")

    scan = _scan_path(result_id)
    if not scan.exists():
        raise HTTPException(404, "Original scan not available for this result")

    raw = scan.read_bytes()
    arr = np.frombuffer(raw, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(422, "Could not decode stored scan")

    rectified, *_ = _rectify(img)
    new_centering = measure_centering_color_hint(
        rectified, (body.border_r, body.border_g, body.border_b)
    )

    # Determine which method actually ran (colour vs gradient fallback)
    # by checking whether the result differs meaningfully from the stored values
    method = "color_hint"
    if (abs(new_centering.left_pct - result.centering_left_pct) < 0.5
            and abs(new_centering.top_pct - result.centering_top_pct) < 0.5):
        method = "gradient_fallback"

    # Rebuild a minimal surface / corner object for grade recomputation
    from .analyzer import CornerResult, SurfaceResult
    corners = CornerResult(
        top_left=result.corner_tl, top_right=result.corner_tr,
        bottom_left=result.corner_bl, bottom_right=result.corner_br,
        score=result.corner_score,
    )
    surface = SurfaceResult(
        texture_score=result.surface_score,
        scratch_risk=result.surface_scratch_risk,
        score=result.surface_score,
        flags=[],
    )
    new_grade, new_label = _compute_grade(new_centering, corners, surface, result.edge_score)

    # Persist updated centering + grade
    result.centering_left_pct   = new_centering.left_pct
    result.centering_right_pct  = new_centering.right_pct
    result.centering_top_pct    = new_centering.top_pct
    result.centering_bottom_pct = new_centering.bottom_pct
    result.centering_score      = new_centering.score
    result.estimated_grade      = new_grade
    result.grade_label          = new_label
    session.add(result)
    session.commit()

    return RecenterOut(
        centering=CenteringOut(
            left_pct=new_centering.left_pct,
            right_pct=new_centering.right_pct,
            top_pct=new_centering.top_pct,
            bottom_pct=new_centering.bottom_pct,
            lr_ratio=new_centering.lr_ratio,
            tb_ratio=new_centering.tb_ratio,
            score=new_centering.score,
        ),
        estimated_grade=new_grade,
        grade_label=new_label,
        method=method,
    )


# ---------------------------------------------------------------------------
# Provider accuracy stats
# ---------------------------------------------------------------------------

@router.get("/provider-stats", response_model=list[ProviderStatsOut])
def provider_stats(
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(require_grading),
):
    """
    Per-provider identification accuracy, aggregated from all transfers where
    the user confirmed or corrected the auto-identified card info.

    Accuracy is only computed for attempts where ground truth is known
    (i.e. the user has transferred the card). Attempts not yet transferred
    appear in total_attempts but not in *_evaluated counts.
    """
    # Fetch all attempts for this org's grade results (IdentificationAttempt has
    # no org_id of its own — scope via the joined CardGradeResult).
    attempts = session.exec(
        select(IdentificationAttempt)
        .join(CardGradeResult,
              IdentificationAttempt.grade_result_id == CardGradeResult.id)
        .where(CardGradeResult.org_id == ctx.org_id)
    ).all()

    if not attempts:
        return []

    # Group by provider
    from collections import defaultdict
    groups: dict[str, list[IdentificationAttempt]] = defaultdict(list)
    for a in attempts:
        groups[a.provider].append(a)

    stats: list[ProviderStatsOut] = []
    for provider, rows in sorted(groups.items()):
        name_evals   = [r for r in rows if r.name_correct is not None]
        number_evals = [r for r in rows if r.number_correct is not None]

        stats.append(ProviderStatsOut(
            provider=provider,
            total_attempts=len(rows),
            name_evaluated=len(name_evals),
            name_accuracy=(
                round(sum(r.name_correct for r in name_evals) / len(name_evals), 3)
                if name_evals else None
            ),
            number_evaluated=len(number_evals),
            number_accuracy=(
                round(sum(r.number_correct for r in number_evals) / len(number_evals), 3)
                if number_evals else None
            ),
        ))

    return stats


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------

@router.post("/{result_id}/feedback", response_model=FeedbackOut, status_code=201)
def submit_feedback(
    result_id: int,
    body: FeedbackIn,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    ctx: OrgContext = Depends(require_grading),
):
    """
    Attach human feedback to a prior grading result.
    One record per (user, result) — resubmitting replaces the previous one.
    """
    result = session.get(CardGradeResult, result_id)
    if not result:
        raise HTTPException(404, f"Grade result {result_id} not found")
    if result.org_id != ctx.org_id:
        raise HTTPException(403, "Cannot submit feedback on another organization's result")

    existing = session.exec(
        select(GradeFeedback).where(
            GradeFeedback.grade_result_id == result_id,
            GradeFeedback.user_id == current_user.id,
        )
    ).first()

    dims_json = json.dumps(body.inaccurate_dimensions)

    if existing:
        existing.overall_verdict = body.overall_verdict
        existing.actual_grade = body.actual_grade
        existing.grading_company = body.grading_company
        existing.inaccurate_dimensions = dims_json
        existing.notes = body.notes
        fb = existing
    else:
        fb = GradeFeedback(
            grade_result_id=result_id,
            org_id=ctx.org_id,
            user_id=current_user.id,
            overall_verdict=body.overall_verdict,
            actual_grade=body.actual_grade,
            grading_company=body.grading_company,
            inaccurate_dimensions=dims_json,
            notes=body.notes,
        )

    session.add(fb)
    session.commit()
    session.refresh(fb)

    return FeedbackOut(
        id=fb.id,
        grade_result_id=fb.grade_result_id,
        overall_verdict=fb.overall_verdict,
        actual_grade=fb.actual_grade,
        grading_company=fb.grading_company,
        inaccurate_dimensions=json.loads(fb.inaccurate_dimensions or "[]"),
        notes=fb.notes,
        submitted_at=fb.submitted_at,
    )


# ---------------------------------------------------------------------------
# Feedback stats
# ---------------------------------------------------------------------------

@router.get("/feedback/stats", response_model=FeedbackStats)
def feedback_stats(
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(require_grading),
):
    """Aggregate accuracy statistics derived from human feedback."""
    total_analyses = session.exec(
        select(func.count()).select_from(CardGradeResult)
        .where(CardGradeResult.org_id == ctx.org_id)
    ).one()

    feedbacks = session.exec(
        select(GradeFeedback).where(GradeFeedback.org_id == ctx.org_id)
    ).all()

    total_feedback = len(feedbacks)
    feedback_rate = round(total_feedback / total_analyses, 3) if total_analyses else 0.0

    if not feedbacks:
        return FeedbackStats(
            total_analyses=total_analyses,
            total_feedback=0,
            feedback_rate=0.0,
            accurate_pct=0.0,
            too_high_pct=0.0,
            too_low_pct=0.0,
            graded_count=0,
            mean_error=None,
            mean_abs_error=None,
            dimension_accuracy=[],
        )

    verdicts = [f.overall_verdict for f in feedbacks]
    accurate_pct  = round(verdicts.count("accurate")  / total_feedback * 100, 1)
    too_high_pct  = round(verdicts.count("too_high")  / total_feedback * 100, 1)
    too_low_pct   = round(verdicts.count("too_low")   / total_feedback * 100, 1)

    result_ids = [f.grade_result_id for f in feedbacks]
    results_map = {
        r.id: r for r in session.exec(
            select(CardGradeResult).where(CardGradeResult.id.in_(result_ids))
        ).all()
    }

    errors = [
        results_map[f.grade_result_id].estimated_grade - f.actual_grade
        for f in feedbacks
        if f.actual_grade is not None and f.grade_result_id in results_map
    ]
    graded_count    = len(errors)
    mean_error      = round(sum(errors) / graded_count, 3) if errors else None
    mean_abs_error  = round(sum(abs(e) for e in errors) / graded_count, 3) if errors else None

    all_dims = ["centering", "corners", "surface", "edges"]
    dim_counts = {d: 0 for d in all_dims}
    for f in feedbacks:
        for d in json.loads(f.inaccurate_dimensions or "[]"):
            if d in dim_counts:
                dim_counts[d] += 1

    dimension_accuracy = [
        DimensionAccuracy(
            dimension=d,
            times_flagged=dim_counts[d],
            flag_rate=round(dim_counts[d] / total_feedback, 3),
        )
        for d in all_dims
    ]

    return FeedbackStats(
        total_analyses=total_analyses,
        total_feedback=total_feedback,
        feedback_rate=feedback_rate,
        accurate_pct=accurate_pct,
        too_high_pct=too_high_pct,
        too_low_pct=too_low_pct,
        graded_count=graded_count,
        mean_error=mean_error,
        mean_abs_error=mean_abs_error,
        dimension_accuracy=dimension_accuracy,
    )


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

@router.get("/history", response_model=list[GradeResultOut])
def grade_history(
    card_id: Optional[str] = Query(None),
    asset_id: Optional[int] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(require_grading),
):
    """Return past grade analyses for the current organization, optionally filtered."""
    stmt = select(CardGradeResult).where(CardGradeResult.org_id == ctx.org_id)
    if card_id:
        stmt = stmt.where(CardGradeResult.card_id == card_id)
    if asset_id:
        stmt = stmt.where(CardGradeResult.asset_id == asset_id)
    stmt = stmt.order_by(CardGradeResult.analyzed_at.desc()).limit(limit).offset(offset)
    return [_result_to_out(r) for r in session.exec(stmt).all()]
