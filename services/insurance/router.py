"""
Insurance & Appraisals — router, mounted at /insurance.

Tracks insurance policies covering a user's collection (provider, policy
number, coverage, premium, renewal dates, document), itemized "scheduled"
coverage linking a policy to a specific CustomAsset (PolicyItem), and
standalone or asset-linked appraisal records (Appraisal). Ownership is
enforced via _assert_owner() on every route; static routes (/summary,
/policies, /appraisals) come before dynamic /{id} routes, per
docs/MODULE_DEVELOPMENT.md conventions.
"""
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlmodel import Session, select

from services.shared.database import get_session
from services.shared.models import User
from services.auth.middleware import get_current_user
from services.auth.org_context import OrgContext, get_current_org
from services.custom_assets.models import CustomAsset
from .models import Appraisal, InsurancePolicy, PolicyItem
from .schemas import (
    AppraisalCreate,
    AppraisalOut,
    AppraisalUpdate,
    InsurancePolicyCreate,
    InsurancePolicyDetailOut,
    InsurancePolicyOut,
    InsurancePolicyUpdate,
    InsuranceSummary,
    PolicyItemIn,
    PolicyItemOut,
    PolicyItemUpdate,
)

router = APIRouter(tags=["insurance"])

_DOC_UPLOADS = Path("/app/uploads/insurance")
_DOC_TYPES = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
_MAX_DOC_BYTES = 10 * 1024 * 1024  # 10 MB


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _assert_owner(row, ctx: OrgContext) -> None:
    if row.org_id != ctx.org_id:
        raise HTTPException(403, "Cannot access another organization's record")


def _validate_asset_id(asset_id: Optional[int], session: Session, ctx: OrgContext) -> None:
    if asset_id is None:
        return
    asset = session.get(CustomAsset, asset_id)
    if not asset:
        raise HTTPException(404, f"Asset {asset_id} not found")
    if asset.org_id != ctx.org_id:
        raise HTTPException(403, "Cannot link another organization's asset")


def _validate_appraisal_id(appraisal_id: Optional[int], session: Session, ctx: OrgContext) -> None:
    if appraisal_id is None:
        return
    appraisal = session.get(Appraisal, appraisal_id)
    if not appraisal:
        raise HTTPException(404, f"Appraisal {appraisal_id} not found")
    _assert_owner(appraisal, ctx)


def _policy_out(policy: InsurancePolicy) -> InsurancePolicyOut:
    return InsurancePolicyOut(**policy.model_dump())


def _appraisal_out(appraisal: Appraisal) -> AppraisalOut:
    return AppraisalOut(**appraisal.model_dump())


def _item_out(item: PolicyItem) -> PolicyItemOut:
    return PolicyItemOut(**item.model_dump())


async def _save_document(subdir: str, record_id: int, file: UploadFile) -> tuple[str, str]:
    ext = _DOC_TYPES.get(file.content_type or "")
    if not ext:
        raise HTTPException(400, "Document must be PDF, JPEG, PNG, or WebP")

    raw = await file.read()
    if len(raw) > _MAX_DOC_BYTES:
        raise HTTPException(413, "Document exceeds 10 MB limit")

    target_dir = _DOC_UPLOADS / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{record_id}{ext}"
    (target_dir / filename).write_bytes(raw)

    return f"/uploads/insurance/{subdir}/{filename}", (file.filename or filename)


def _cleanup_document(subdir: str, record_id: int) -> None:
    for f in (_DOC_UPLOADS / subdir).glob(f"{record_id}.*"):
        f.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Summary  (static — before any dynamic routes)
# ---------------------------------------------------------------------------

@router.get("/summary", response_model=InsuranceSummary)
def insurance_summary(
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(get_current_org),
):
    policies = session.exec(
        select(InsurancePolicy).where(InsurancePolicy.org_id == ctx.org_id)
    ).all()
    appraisals = session.exec(
        select(Appraisal).where(Appraisal.org_id == ctx.org_id)
    ).all()
    items = session.exec(
        select(PolicyItem).where(PolicyItem.org_id == ctx.org_id)
    ).all()

    today = date.today().isoformat()
    cutoff = (date.today() + timedelta(days=60)).isoformat()
    expiring = sum(1 for p in policies if p.end_date and today <= p.end_date <= cutoff)

    return InsuranceSummary(
        policy_count=len(policies),
        appraisal_count=len(appraisals),
        total_coverage=sum(p.coverage_amount or 0 for p in policies),
        total_scheduled=sum(i.scheduled_amount or 0 for i in items),
        policies_expiring_soon=expiring,
    )


# ---------------------------------------------------------------------------
# Policies
# ---------------------------------------------------------------------------

@router.get("/policies", response_model=list[InsurancePolicyOut])
def list_policies(
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(get_current_org),
):
    policies = session.exec(
        select(InsurancePolicy)
        .where(InsurancePolicy.org_id == ctx.org_id)
        .order_by(InsurancePolicy.created_at.desc())
    ).all()
    return [_policy_out(p) for p in policies]


@router.post("/policies", response_model=InsurancePolicyOut, status_code=201)
def create_policy(
    body: InsurancePolicyCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    ctx: OrgContext = Depends(get_current_org),
):
    policy = InsurancePolicy(
        org_id=ctx.org_id, user_id=current_user.id, **body.model_dump()
    )
    session.add(policy)
    session.commit()
    session.refresh(policy)
    return _policy_out(policy)


@router.get("/policies/{policy_id}", response_model=InsurancePolicyDetailOut)
def get_policy(
    policy_id: int,
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(get_current_org),
):
    policy = session.get(InsurancePolicy, policy_id)
    if not policy:
        raise HTTPException(404, f"Policy {policy_id} not found")
    _assert_owner(policy, ctx)

    items = session.exec(
        select(PolicyItem).where(PolicyItem.policy_id == policy_id)
    ).all()
    return InsurancePolicyDetailOut(**policy.model_dump(), items=[_item_out(i) for i in items])


@router.patch("/policies/{policy_id}", response_model=InsurancePolicyOut)
def update_policy(
    policy_id: int,
    body: InsurancePolicyUpdate,
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(get_current_org),
):
    policy = session.get(InsurancePolicy, policy_id)
    if not policy:
        raise HTTPException(404, f"Policy {policy_id} not found")
    _assert_owner(policy, ctx)

    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(policy, field, val)
    policy.updated_at = datetime.utcnow()

    session.add(policy)
    session.commit()
    session.refresh(policy)
    return _policy_out(policy)


@router.delete("/policies/{policy_id}", status_code=204)
def delete_policy(
    policy_id: int,
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(get_current_org),
):
    policy = session.get(InsurancePolicy, policy_id)
    if not policy:
        raise HTTPException(404, f"Policy {policy_id} not found")
    _assert_owner(policy, ctx)

    items = session.exec(
        select(PolicyItem).where(PolicyItem.policy_id == policy_id)
    ).all()
    for item in items:
        session.delete(item)
    session.flush()  # send item deletes before the FK-constrained policy delete
    session.delete(policy)
    session.commit()
    _cleanup_document("policies", policy_id)


@router.post("/policies/{policy_id}/document")
async def upload_policy_document(
    policy_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(get_current_org),
):
    policy = session.get(InsurancePolicy, policy_id)
    if not policy:
        raise HTTPException(404, f"Policy {policy_id} not found")
    _assert_owner(policy, ctx)

    url, filename = await _save_document("policies", policy_id, file)
    policy.document_url = url
    policy.document_filename = filename
    policy.updated_at = datetime.utcnow()
    session.add(policy)
    session.commit()
    return {"document_url": url, "document_filename": filename}


# ---------------------------------------------------------------------------
# Scheduled items (nested under a policy)
# ---------------------------------------------------------------------------

@router.post("/policies/{policy_id}/items", response_model=PolicyItemOut, status_code=201)
def add_policy_item(
    policy_id: int,
    body: PolicyItemIn,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    ctx: OrgContext = Depends(get_current_org),
):
    policy = session.get(InsurancePolicy, policy_id)
    if not policy:
        raise HTTPException(404, f"Policy {policy_id} not found")
    _assert_owner(policy, ctx)

    _validate_asset_id(body.asset_id, session, ctx)
    _validate_appraisal_id(body.appraisal_id, session, ctx)

    item = PolicyItem(
        policy_id=policy_id, org_id=ctx.org_id, user_id=current_user.id, **body.model_dump()
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return _item_out(item)


@router.patch("/policies/{policy_id}/items/{item_id}", response_model=PolicyItemOut)
def update_policy_item(
    policy_id: int,
    item_id: int,
    body: PolicyItemUpdate,
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(get_current_org),
):
    item = session.get(PolicyItem, item_id)
    if not item or item.policy_id != policy_id:
        raise HTTPException(404, f"Item {item_id} not found on policy {policy_id}")
    _assert_owner(item, ctx)

    updates = body.model_dump(exclude_unset=True)
    if "asset_id" in updates:
        _validate_asset_id(updates["asset_id"], session, ctx)
    if "appraisal_id" in updates:
        _validate_appraisal_id(updates["appraisal_id"], session, ctx)

    for field, val in updates.items():
        setattr(item, field, val)

    session.add(item)
    session.commit()
    session.refresh(item)
    return _item_out(item)


@router.delete("/policies/{policy_id}/items/{item_id}", status_code=204)
def delete_policy_item(
    policy_id: int,
    item_id: int,
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(get_current_org),
):
    item = session.get(PolicyItem, item_id)
    if not item or item.policy_id != policy_id:
        raise HTTPException(404, f"Item {item_id} not found on policy {policy_id}")
    _assert_owner(item, ctx)

    session.delete(item)
    session.commit()


# ---------------------------------------------------------------------------
# Appraisals
# ---------------------------------------------------------------------------

@router.get("/appraisals", response_model=list[AppraisalOut])
def list_appraisals(
    asset_id: Optional[int] = Query(None),
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(get_current_org),
):
    stmt = select(Appraisal).where(Appraisal.org_id == ctx.org_id)
    if asset_id is not None:
        stmt = stmt.where(Appraisal.asset_id == asset_id)
    stmt = stmt.order_by(Appraisal.created_at.desc())
    appraisals = session.exec(stmt).all()
    return [_appraisal_out(a) for a in appraisals]


@router.post("/appraisals", response_model=AppraisalOut, status_code=201)
def create_appraisal(
    body: AppraisalCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    ctx: OrgContext = Depends(get_current_org),
):
    _validate_asset_id(body.asset_id, session, ctx)

    appraisal = Appraisal(org_id=ctx.org_id, user_id=current_user.id, **body.model_dump())
    session.add(appraisal)
    session.commit()
    session.refresh(appraisal)
    return _appraisal_out(appraisal)


@router.patch("/appraisals/{appraisal_id}", response_model=AppraisalOut)
def update_appraisal(
    appraisal_id: int,
    body: AppraisalUpdate,
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(get_current_org),
):
    appraisal = session.get(Appraisal, appraisal_id)
    if not appraisal:
        raise HTTPException(404, f"Appraisal {appraisal_id} not found")
    _assert_owner(appraisal, ctx)

    updates = body.model_dump(exclude_unset=True)
    if "asset_id" in updates:
        _validate_asset_id(updates["asset_id"], session, ctx)

    for field, val in updates.items():
        setattr(appraisal, field, val)
    appraisal.updated_at = datetime.utcnow()

    session.add(appraisal)
    session.commit()
    session.refresh(appraisal)
    return _appraisal_out(appraisal)


@router.delete("/appraisals/{appraisal_id}", status_code=204)
def delete_appraisal(
    appraisal_id: int,
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(get_current_org),
):
    appraisal = session.get(Appraisal, appraisal_id)
    if not appraisal:
        raise HTTPException(404, f"Appraisal {appraisal_id} not found")
    _assert_owner(appraisal, ctx)

    # Detach any PolicyItems that reference this appraisal as supporting evidence
    items = session.exec(
        select(PolicyItem).where(PolicyItem.appraisal_id == appraisal_id)
    ).all()
    for item in items:
        item.appraisal_id = None
        session.add(item)
    session.flush()

    session.delete(appraisal)
    session.commit()
    _cleanup_document("appraisals", appraisal_id)


@router.post("/appraisals/{appraisal_id}/document")
async def upload_appraisal_document(
    appraisal_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    ctx: OrgContext = Depends(get_current_org),
):
    appraisal = session.get(Appraisal, appraisal_id)
    if not appraisal:
        raise HTTPException(404, f"Appraisal {appraisal_id} not found")
    _assert_owner(appraisal, ctx)

    url, filename = await _save_document("appraisals", appraisal_id, file)
    appraisal.document_url = url
    appraisal.document_filename = filename
    appraisal.updated_at = datetime.utcnow()
    session.add(appraisal)
    session.commit()
    return {"document_url": url, "document_filename": filename}
