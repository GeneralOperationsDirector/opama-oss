"""
Vehicle Maintenance — router, mounted at /vehicles.

Tracks a service/maintenance log (ServiceRecord) and registration/title/
insurance-card/inspection documents (VehicleDocument) for vehicles tracked
as CustomAsset rows. Every record is linked to exactly one asset_id.
Ownership is enforced via _assert_owner() on every route; static routes
(/summary, /service-records, /documents) come before dynamic /{id} routes,
per docs/MODULE_DEVELOPMENT.md conventions.
"""
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlmodel import Session, or_, select

from services.shared.database import get_session
from services.shared.models import User
from services.auth.middleware import get_current_user
from services.custom_assets.models import CustomAsset
from .models import ServiceRecord, VehicleDocument
from .schemas import (
    ServiceRecordCreate,
    ServiceRecordOut,
    ServiceRecordUpdate,
    VehicleDocumentCreate,
    VehicleDocumentOut,
    VehicleDocumentUpdate,
    VehicleSummary,
)

router = APIRouter(tags=["vehicles"])

_DOC_UPLOADS = Path("/app/uploads/vehicles")
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


def _record_out(record: ServiceRecord) -> ServiceRecordOut:
    return ServiceRecordOut(**record.model_dump())


def _document_out(doc: VehicleDocument) -> VehicleDocumentOut:
    return VehicleDocumentOut(**doc.model_dump())


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

    return f"/uploads/vehicles/{subdir}/{filename}", (file.filename or filename)


def _cleanup_document(subdir: str, record_id: int) -> None:
    for f in (_DOC_UPLOADS / subdir).glob(f"{record_id}.*"):
        f.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Summary  (static — before any dynamic routes)
# ---------------------------------------------------------------------------

@router.get("/summary", response_model=VehicleSummary)
def vehicle_summary(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    vehicle_count = len(session.exec(
        select(CustomAsset)
        .where(CustomAsset.user_id == current_user.id)
        .where(or_(CustomAsset.category.ilike("vehicle"), CustomAsset.category.ilike("bicycle")))
    ).all())

    records = session.exec(
        select(ServiceRecord).where(ServiceRecord.user_id == current_user.id)
    ).all()

    documents = session.exec(
        select(VehicleDocument).where(VehicleDocument.user_id == current_user.id)
    ).all()

    today = date.today().isoformat()
    cutoff = (date.today() + timedelta(days=60)).isoformat()
    expiring = sum(1 for d in documents if d.expiry_date and today <= d.expiry_date <= cutoff)

    return VehicleSummary(
        vehicle_count=vehicle_count,
        total_service_cost=sum(r.cost or 0 for r in records),
        service_record_count=len(records),
        documents_expiring_soon=expiring,
    )


# ---------------------------------------------------------------------------
# Service records
# ---------------------------------------------------------------------------

@router.get("/service-records", response_model=list[ServiceRecordOut])
def list_service_records(
    asset_id: Optional[int] = Query(None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    stmt = select(ServiceRecord).where(ServiceRecord.user_id == current_user.id)
    if asset_id is not None:
        stmt = stmt.where(ServiceRecord.asset_id == asset_id)
    stmt = stmt.order_by(ServiceRecord.created_at.desc())
    records = session.exec(stmt).all()
    return [_record_out(r) for r in records]


@router.post("/service-records", response_model=ServiceRecordOut, status_code=201)
def create_service_record(
    body: ServiceRecordCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _validate_asset_id(body.asset_id, session, current_user)

    record = ServiceRecord(user_id=current_user.id, **body.model_dump())
    session.add(record)
    session.commit()
    session.refresh(record)
    return _record_out(record)


@router.patch("/service-records/{record_id}", response_model=ServiceRecordOut)
def update_service_record(
    record_id: int,
    body: ServiceRecordUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    record = session.get(ServiceRecord, record_id)
    if not record:
        raise HTTPException(404, f"Service record {record_id} not found")
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
    return _record_out(record)


@router.delete("/service-records/{record_id}", status_code=204)
def delete_service_record(
    record_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    record = session.get(ServiceRecord, record_id)
    if not record:
        raise HTTPException(404, f"Service record {record_id} not found")
    _assert_owner(record, current_user)

    session.delete(record)
    session.commit()
    _cleanup_document("service_records", record_id)


@router.post("/service-records/{record_id}/document")
async def upload_service_record_document(
    record_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    record = session.get(ServiceRecord, record_id)
    if not record:
        raise HTTPException(404, f"Service record {record_id} not found")
    _assert_owner(record, current_user)

    url, filename = await _save_document("service_records", record_id, file)
    record.document_url = url
    record.document_filename = filename
    record.updated_at = datetime.utcnow()
    session.add(record)
    session.commit()
    return {"document_url": url, "document_filename": filename}


# ---------------------------------------------------------------------------
# Vehicle documents (registration, title, insurance card, inspection, ...)
# ---------------------------------------------------------------------------

@router.get("/documents", response_model=list[VehicleDocumentOut])
def list_vehicle_documents(
    asset_id: Optional[int] = Query(None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    stmt = select(VehicleDocument).where(VehicleDocument.user_id == current_user.id)
    if asset_id is not None:
        stmt = stmt.where(VehicleDocument.asset_id == asset_id)
    stmt = stmt.order_by(VehicleDocument.created_at.desc())
    documents = session.exec(stmt).all()
    return [_document_out(d) for d in documents]


@router.post("/documents", response_model=VehicleDocumentOut, status_code=201)
def create_vehicle_document(
    body: VehicleDocumentCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    _validate_asset_id(body.asset_id, session, current_user)

    document = VehicleDocument(user_id=current_user.id, **body.model_dump())
    session.add(document)
    session.commit()
    session.refresh(document)
    return _document_out(document)


@router.patch("/documents/{document_id}", response_model=VehicleDocumentOut)
def update_vehicle_document(
    document_id: int,
    body: VehicleDocumentUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    document = session.get(VehicleDocument, document_id)
    if not document:
        raise HTTPException(404, f"Document {document_id} not found")
    _assert_owner(document, current_user)

    updates = body.model_dump(exclude_unset=True)
    if "asset_id" in updates:
        _validate_asset_id(updates["asset_id"], session, current_user)

    for field, val in updates.items():
        setattr(document, field, val)
    document.updated_at = datetime.utcnow()

    session.add(document)
    session.commit()
    session.refresh(document)
    return _document_out(document)


@router.delete("/documents/{document_id}", status_code=204)
def delete_vehicle_document(
    document_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    document = session.get(VehicleDocument, document_id)
    if not document:
        raise HTTPException(404, f"Document {document_id} not found")
    _assert_owner(document, current_user)

    session.delete(document)
    session.commit()
    _cleanup_document("documents", document_id)


@router.post("/documents/{document_id}/document")
async def upload_vehicle_document_file(
    document_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    document = session.get(VehicleDocument, document_id)
    if not document:
        raise HTTPException(404, f"Document {document_id} not found")
    _assert_owner(document, current_user)

    url, filename = await _save_document("documents", document_id, file)
    document.document_url = url
    document.document_filename = filename
    document.updated_at = datetime.utcnow()
    session.add(document)
    session.commit()
    return {"document_url": url, "document_filename": filename}
