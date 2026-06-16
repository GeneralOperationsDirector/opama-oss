from typing import Optional
from datetime import datetime
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Service records
# ---------------------------------------------------------------------------

class ServiceRecordCreate(BaseModel):
    asset_id: int
    service_date: Optional[str] = None
    odometer: Optional[int] = None
    service_type: str
    cost: Optional[float] = None
    vendor: Optional[str] = None
    notes: Optional[str] = None


class ServiceRecordUpdate(BaseModel):
    asset_id: Optional[int] = None
    service_date: Optional[str] = None
    odometer: Optional[int] = None
    service_type: Optional[str] = None
    cost: Optional[float] = None
    vendor: Optional[str] = None
    notes: Optional[str] = None


class ServiceRecordOut(BaseModel):
    id: int
    user_id: int
    asset_id: int
    service_date: Optional[str]
    odometer: Optional[int]
    service_type: str
    cost: Optional[float]
    vendor: Optional[str]
    notes: Optional[str]
    document_url: Optional[str]
    document_filename: Optional[str]
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Vehicle documents
# ---------------------------------------------------------------------------

class VehicleDocumentCreate(BaseModel):
    asset_id: int
    doc_type: str
    issued_date: Optional[str] = None
    expiry_date: Optional[str] = None
    notes: Optional[str] = None


class VehicleDocumentUpdate(BaseModel):
    asset_id: Optional[int] = None
    doc_type: Optional[str] = None
    issued_date: Optional[str] = None
    expiry_date: Optional[str] = None
    notes: Optional[str] = None


class VehicleDocumentOut(BaseModel):
    id: int
    user_id: int
    asset_id: int
    doc_type: str
    issued_date: Optional[str]
    expiry_date: Optional[str]
    document_url: Optional[str]
    document_filename: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

class VehicleSummary(BaseModel):
    vehicle_count: int
    total_service_cost: float
    service_record_count: int
    documents_expiring_soon: int  # within 60 days
