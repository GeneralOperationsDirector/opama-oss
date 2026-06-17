"""
Vehicle Maintenance — SQLModel tables.

Two tables, each linked to a specific CustomAsset (a vehicle the user owns
via the "Vehicle" collection template):

- ServiceRecord: a maintenance/service log entry (date, odometer, type,
  cost, vendor, receipt document).
- VehicleDocument: a registration, title, inspection, or insurance-card
  document with optional issue/expiry dates.

Unlike Insurance (where asset_id is optional), every record here belongs to
exactly one vehicle, so asset_id is required. user_id is denormalized for
O(1) ownership checks, consistent with every other table in the codebase.
"""

from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field


class ServiceRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    # Ownership/RLS scope (pool tenancy — see pool_vs_silo); nullable through backfill.
    org_id: int = Field(foreign_key="organization.id", index=True)
    user_id: int = Field(index=True)
    asset_id: int = Field(foreign_key="customasset.id", ondelete="CASCADE", index=True)

    service_date: Optional[str] = None  # ISO date YYYY-MM-DD
    odometer: Optional[int] = None
    service_type: str  # e.g. "Oil Change", "Tire Rotation", "Brake Service"
    cost: Optional[float] = None
    vendor: Optional[str] = None
    notes: Optional[str] = None

    document_url: Optional[str] = None
    document_filename: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class VehicleDocument(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    org_id: int = Field(foreign_key="organization.id", index=True)
    user_id: int = Field(index=True)
    asset_id: int = Field(foreign_key="customasset.id", ondelete="CASCADE", index=True)

    doc_type: str  # e.g. "Registration", "Title", "Insurance Card", "Inspection"
    issued_date: Optional[str] = None  # ISO date YYYY-MM-DD
    expiry_date: Optional[str] = None  # ISO date — used for "expiring soon"

    document_url: Optional[str] = None
    document_filename: Optional[str] = None
    notes: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
