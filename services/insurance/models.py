"""
Insurance & Appraisals — SQLModel tables.

Three tables:
- InsurancePolicy: a user's insurance policy covering their collection
  (provider, policy number, coverage, premium, renewal dates, document).
- Appraisal: a standalone or asset-linked appraisal record (appraiser,
  value, date, document). May be referenced by a PolicyItem as supporting
  evidence for a scheduled coverage amount.
- PolicyItem: itemized "scheduled" coverage linking a policy to a specific
  CustomAsset (or a free-text description if the item isn't in Collections
  yet), optionally backed by an Appraisal.

user_id is denormalized onto PolicyItem and Appraisal (not just reachable via
policy_id/asset_id) so ownership checks stay O(1), consistent with every
other table in the codebase.
"""

from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field


class InsurancePolicy(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    # Ownership/RLS scope (pool tenancy — see pool_vs_silo); nullable through backfill.
    org_id: int = Field(foreign_key="organization.id", index=True)
    user_id: int = Field(index=True)

    provider: str
    policy_number: Optional[str] = None
    policy_type: Optional[str] = None  # e.g. "homeowners", "renters", "valuable items rider"

    coverage_amount: Optional[float] = None  # overall policy limit
    deductible: Optional[float] = None
    premium_amount: Optional[float] = None
    premium_frequency: Optional[str] = None  # "monthly" | "annual"

    start_date: Optional[str] = None  # ISO date YYYY-MM-DD
    end_date: Optional[str] = None    # ISO date — renewal/expiry

    document_url: Optional[str] = None
    document_filename: Optional[str] = None
    notes: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Appraisal(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    org_id: int = Field(foreign_key="organization.id", index=True)
    user_id: int = Field(index=True)
    asset_id: Optional[int] = Field(default=None, foreign_key="customasset.id", index=True)

    appraiser_name: Optional[str] = None
    appraised_value: float
    appraisal_date: Optional[str] = None  # ISO date YYYY-MM-DD

    document_url: Optional[str] = None
    document_filename: Optional[str] = None
    notes: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class PolicyItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    org_id: int = Field(foreign_key="organization.id", index=True)
    policy_id: int = Field(foreign_key="insurancepolicy.id", index=True)
    user_id: int = Field(index=True)
    asset_id: Optional[int] = Field(default=None, foreign_key="customasset.id", index=True)
    appraisal_id: Optional[int] = Field(default=None, foreign_key="appraisal.id")

    description: str  # free-text label, used when asset_id is null
    scheduled_amount: Optional[float] = None  # per-item coverage limit

    created_at: datetime = Field(default_factory=datetime.utcnow)
