from typing import Optional
from datetime import datetime
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Insurance policies
# ---------------------------------------------------------------------------

class PolicyItemIn(BaseModel):
    asset_id: Optional[int] = None
    appraisal_id: Optional[int] = None
    description: str
    scheduled_amount: Optional[float] = None


class PolicyItemUpdate(BaseModel):
    asset_id: Optional[int] = None
    appraisal_id: Optional[int] = None
    description: Optional[str] = None
    scheduled_amount: Optional[float] = None


class PolicyItemOut(BaseModel):
    id: int
    policy_id: int
    asset_id: Optional[int]
    appraisal_id: Optional[int]
    description: str
    scheduled_amount: Optional[float]


class InsurancePolicyCreate(BaseModel):
    provider: str
    policy_number: Optional[str] = None
    policy_type: Optional[str] = None
    coverage_amount: Optional[float] = None
    deductible: Optional[float] = None
    premium_amount: Optional[float] = None
    premium_frequency: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    notes: Optional[str] = None


class InsurancePolicyUpdate(BaseModel):
    provider: Optional[str] = None
    policy_number: Optional[str] = None
    policy_type: Optional[str] = None
    coverage_amount: Optional[float] = None
    deductible: Optional[float] = None
    premium_amount: Optional[float] = None
    premium_frequency: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    notes: Optional[str] = None


class InsurancePolicyOut(BaseModel):
    id: int
    user_id: int
    provider: str
    policy_number: Optional[str]
    policy_type: Optional[str]
    coverage_amount: Optional[float]
    deductible: Optional[float]
    premium_amount: Optional[float]
    premium_frequency: Optional[str]
    start_date: Optional[str]
    end_date: Optional[str]
    document_url: Optional[str]
    document_filename: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


class InsurancePolicyDetailOut(InsurancePolicyOut):
    items: list[PolicyItemOut] = []


# ---------------------------------------------------------------------------
# Appraisals
# ---------------------------------------------------------------------------

class AppraisalCreate(BaseModel):
    asset_id: Optional[int] = None
    appraiser_name: Optional[str] = None
    appraised_value: float
    appraisal_date: Optional[str] = None
    notes: Optional[str] = None


class AppraisalUpdate(BaseModel):
    asset_id: Optional[int] = None
    appraiser_name: Optional[str] = None
    appraised_value: Optional[float] = None
    appraisal_date: Optional[str] = None
    notes: Optional[str] = None


class AppraisalOut(BaseModel):
    id: int
    user_id: int
    asset_id: Optional[int]
    appraiser_name: Optional[str]
    appraised_value: float
    appraisal_date: Optional[str]
    document_url: Optional[str]
    document_filename: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

class InsuranceSummary(BaseModel):
    policy_count: int
    appraisal_count: int
    total_coverage: float
    total_scheduled: float
    policies_expiring_soon: int  # within 60 days
