"""
Property Records — router, mounted at /real-estate.

Tracks mortgage loans (MortgageLoan), valuation history (PropertyValuation),
and property tax records (PropertyTaxRecord) for properties tracked as
CustomAsset rows. Every record is linked to exactly one asset_id. Ownership
is enforced via _assert_owner() on every route; static routes (/summary,
/mortgages, /valuations, /tax-records) come before dynamic /{id} routes,
per docs/MODULE_DEVELOPMENT.md conventions.
"""
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlmodel import Session, select

from services.shared.database import get_session
from services.shared.models import User
from services.auth.middleware import get_current_user
from services.custom_assets.models import CustomAsset
from .models import MortgageLoan, PropertyTaxRecord, PropertyValuation
from .schemas import (
    MortgageLoanCreate,
    MortgageLoanOut,
    MortgageLoanUpdate,
    PropertyTaxRecordCreate,
    PropertyTaxRecordOut,
    PropertyTaxRecordUpdate,
    PropertyValuationCreate,
    PropertyValuationOut,
    PropertyValuationUpdate,
    RealEstateSummary,
)

router = APIRouter(tags=["real_estate"])

_DOC_UPLOADS = Path("/app/uploads/real_estate")
_DOC_TYPES = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
_MAX_DOC_BYTES = 10 * 1024 * 1024  # 10 MB


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _assert_owner(row, current_user: User) -> None:
    if row.user_id != current_user.id:
        raise HTTPException(403, "Cannot access another user's record")


def _validate_asset_id(asset_id: int, session: Session, current_user: User) -> None:
    asset = session.get(CustomAsset, asset_id)
    if not asset:
        raise HTTPException(404, f"Asset {asset_id} not found")
    if asset.user_id != current_user.id:
        raise HTTPException(403, "Cannot link another user's asset")


def _mortgage_out(loan: MortgageLoan) -> MortgageLoanOut:
    return MortgageLoanOut(**loan.model_dump())


def _valuation_out(val: PropertyValuation) -> PropertyValuationOut:
    return PropertyValuationOut(**val.model_dump())


def _tax_record_out(rec: PropertyTaxRecord) -> PropertyTaxRecordOut:
    return PropertyTaxRecordOut(**rec.model_dump())


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

    return f"/uploads/real_estate/{subdir}/{filename}", (file.filename or filename)


def _cleanup_document(subdir: str, record_id: int) -> None:
    for f in (_DOC_UPLOADS / subdir).glob(f"{record_id}.*"):
        f.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Summary  (static — before any dynamic routes)
# ---------------------------------------------------------------------------

@router.get("/summary", response_model=RealEstateSummary)
def real_estate_summary(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    property_count = len(session.exec(
        select(CustomAsset)
        .where(CustomAsset.user_id == current_user.id)
        .where(CustomAsset.category.ilike("real estate"))
    ).all())

    loans = session.exec(
        select(MortgageLoan).where(MortgageLoan.user_id == current_user.id)
    ).all()
    total_mortgage_balance = sum(l.current_balance or 0 for l in loans)

    valuations = session.exec(
        select(PropertyValuation).where(PropertyValuation.user_id == current_user.id)
    ).all()
    # Most recent valuation per asset (by valuation_date, falling back to id),
    # summed — avoids double-counting historical valuations.
    latest_by_asset: dict[int, PropertyValuation] = {}
    for v in valuations:
        current = latest_by_asset.get(v.asset_id)
        if current is None:
            latest_by_asset[v.asset_id] = v
            continue
        v_date = v.valuation_date or ""
        c_date = current.valuation_date or ""
        if (v_date, v.id) > (c_date, current.id):
            latest_by_asset[v.asset_id] = v
    total_valuation = sum(v.valuation_amount for v in latest_by_asset.values())

    tax_records = session.exec(
        select(PropertyTaxRecord).where(PropertyTaxRecord.user_id == current_user.id)
    ).all()
    today = date.today().isoformat()
    cutoff = (date.today() + timedelta(days=60)).isoformat()
    taxes_due_soon = sum(
        1 for t in tax_records
        if not t.paid and t.due_date and today <= t.due_date <= cutoff
    )

    return RealEstateSummary(
        property_count=property_count,
        total_mortgage_balance=total_mortgage_balance,
        total_valuation=total_valuation,
        estimated_equity=total_valuation - total_mortgage_balance,
        taxes_due_soon=taxes_due_soon,
    )


# ---------------------------------------------------------------------------
# Mortgages
# ---------------------------------------------------------------------------

@router.get("/mortgages", response_model=list[MortgageLoanOut])
def list_mortgages(
    asset_id: Optional[int] = Query(None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    stmt = select(MortgageLoan).where(MortgageLoan.user_id == current_user.id)
    if asset_id is not None:
        stmt = stmt.where(MortgageLoan.asset_id == asset_id)
    stmt = stmt.order_by(MortgageLoan.created_at.desc())
    loans = session.exec(stmt).all()
    return [_mortgage_out(l) for l in loans]


@router.post("/mortgages", response_model=MortgageLoanOut, status_code=201)
def create_mortgage(
    body: MortgageLoanCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _validate_asset_id(body.asset_id, session, current_user)

    loan = MortgageLoan(user_id=current_user.id, **body.model_dump())
    session.add(loan)
    session.commit()
    session.refresh(loan)
    return _mortgage_out(loan)


@router.patch("/mortgages/{loan_id}", response_model=MortgageLoanOut)
def update_mortgage(
    loan_id: int,
    body: MortgageLoanUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    loan = session.get(MortgageLoan, loan_id)
    if not loan:
        raise HTTPException(404, f"Mortgage {loan_id} not found")
    _assert_owner(loan, current_user)

    updates = body.model_dump(exclude_unset=True)
    if "asset_id" in updates:
        _validate_asset_id(updates["asset_id"], session, current_user)

    for field, val in updates.items():
        setattr(loan, field, val)
    loan.updated_at = datetime.utcnow()

    session.add(loan)
    session.commit()
    session.refresh(loan)
    return _mortgage_out(loan)


@router.delete("/mortgages/{loan_id}", status_code=204)
def delete_mortgage(
    loan_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    loan = session.get(MortgageLoan, loan_id)
    if not loan:
        raise HTTPException(404, f"Mortgage {loan_id} not found")
    _assert_owner(loan, current_user)

    session.delete(loan)
    session.commit()
    _cleanup_document("mortgages", loan_id)


@router.post("/mortgages/{loan_id}/document")
async def upload_mortgage_document(
    loan_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    loan = session.get(MortgageLoan, loan_id)
    if not loan:
        raise HTTPException(404, f"Mortgage {loan_id} not found")
    _assert_owner(loan, current_user)

    url, filename = await _save_document("mortgages", loan_id, file)
    loan.document_url = url
    loan.document_filename = filename
    loan.updated_at = datetime.utcnow()
    session.add(loan)
    session.commit()
    return {"document_url": url, "document_filename": filename}


# ---------------------------------------------------------------------------
# Valuations
# ---------------------------------------------------------------------------

@router.get("/valuations", response_model=list[PropertyValuationOut])
def list_valuations(
    asset_id: Optional[int] = Query(None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    stmt = select(PropertyValuation).where(PropertyValuation.user_id == current_user.id)
    if asset_id is not None:
        stmt = stmt.where(PropertyValuation.asset_id == asset_id)
    stmt = stmt.order_by(PropertyValuation.created_at.desc())
    valuations = session.exec(stmt).all()
    return [_valuation_out(v) for v in valuations]


@router.post("/valuations", response_model=PropertyValuationOut, status_code=201)
def create_valuation(
    body: PropertyValuationCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _validate_asset_id(body.asset_id, session, current_user)

    valuation = PropertyValuation(user_id=current_user.id, **body.model_dump())
    session.add(valuation)
    session.commit()
    session.refresh(valuation)
    return _valuation_out(valuation)


@router.patch("/valuations/{valuation_id}", response_model=PropertyValuationOut)
def update_valuation(
    valuation_id: int,
    body: PropertyValuationUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    valuation = session.get(PropertyValuation, valuation_id)
    if not valuation:
        raise HTTPException(404, f"Valuation {valuation_id} not found")
    _assert_owner(valuation, current_user)

    updates = body.model_dump(exclude_unset=True)
    if "asset_id" in updates:
        _validate_asset_id(updates["asset_id"], session, current_user)

    for field, val in updates.items():
        setattr(valuation, field, val)
    valuation.updated_at = datetime.utcnow()

    session.add(valuation)
    session.commit()
    session.refresh(valuation)
    return _valuation_out(valuation)


@router.delete("/valuations/{valuation_id}", status_code=204)
def delete_valuation(
    valuation_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    valuation = session.get(PropertyValuation, valuation_id)
    if not valuation:
        raise HTTPException(404, f"Valuation {valuation_id} not found")
    _assert_owner(valuation, current_user)

    session.delete(valuation)
    session.commit()
    _cleanup_document("valuations", valuation_id)


@router.post("/valuations/{valuation_id}/document")
async def upload_valuation_document(
    valuation_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    valuation = session.get(PropertyValuation, valuation_id)
    if not valuation:
        raise HTTPException(404, f"Valuation {valuation_id} not found")
    _assert_owner(valuation, current_user)

    url, filename = await _save_document("valuations", valuation_id, file)
    valuation.document_url = url
    valuation.document_filename = filename
    valuation.updated_at = datetime.utcnow()
    session.add(valuation)
    session.commit()
    return {"document_url": url, "document_filename": filename}


# ---------------------------------------------------------------------------
# Property tax records
# ---------------------------------------------------------------------------

@router.get("/tax-records", response_model=list[PropertyTaxRecordOut])
def list_tax_records(
    asset_id: Optional[int] = Query(None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    stmt = select(PropertyTaxRecord).where(PropertyTaxRecord.user_id == current_user.id)
    if asset_id is not None:
        stmt = stmt.where(PropertyTaxRecord.asset_id == asset_id)
    stmt = stmt.order_by(PropertyTaxRecord.tax_year.desc())
    records = session.exec(stmt).all()
    return [_tax_record_out(r) for r in records]


@router.post("/tax-records", response_model=PropertyTaxRecordOut, status_code=201)
def create_tax_record(
    body: PropertyTaxRecordCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _validate_asset_id(body.asset_id, session, current_user)

    record = PropertyTaxRecord(user_id=current_user.id, **body.model_dump())
    session.add(record)
    session.commit()
    session.refresh(record)
    return _tax_record_out(record)


@router.patch("/tax-records/{record_id}", response_model=PropertyTaxRecordOut)
def update_tax_record(
    record_id: int,
    body: PropertyTaxRecordUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    record = session.get(PropertyTaxRecord, record_id)
    if not record:
        raise HTTPException(404, f"Tax record {record_id} not found")
    _assert_owner(record, current_user)

    updates = body.model_dump(exclude_unset=True)
    if "asset_id" in updates:
        _validate_asset_id(updates["asset_id"], session, current_user)

    for field, val in updates.items():
        setattr(record, field, val)
    record.updated_at = datetime.utcnow()

    session.add(record)
    session.commit()
    session.refresh(record)
    return _tax_record_out(record)


@router.delete("/tax-records/{record_id}", status_code=204)
def delete_tax_record(
    record_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    record = session.get(PropertyTaxRecord, record_id)
    if not record:
        raise HTTPException(404, f"Tax record {record_id} not found")
    _assert_owner(record, current_user)

    session.delete(record)
    session.commit()
    _cleanup_document("tax_records", record_id)


@router.post("/tax-records/{record_id}/document")
async def upload_tax_record_document(
    record_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    record = session.get(PropertyTaxRecord, record_id)
    if not record:
        raise HTTPException(404, f"Tax record {record_id} not found")
    _assert_owner(record, current_user)

    url, filename = await _save_document("tax_records", record_id, file)
    record.document_url = url
    record.document_filename = filename
    record.updated_at = datetime.utcnow()
    session.add(record)
    session.commit()
    return {"document_url": url, "document_filename": filename}
