from typing import Optional
from datetime import datetime
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Mortgage loans
# ---------------------------------------------------------------------------

class MortgageLoanCreate(BaseModel):
    asset_id: int
    lender: str
    loan_number: Optional[str] = None
    original_amount: Optional[float] = None
    interest_rate: Optional[float] = None
    term_months: Optional[int] = None
    monthly_payment: Optional[float] = None
    start_date: Optional[str] = None
    current_balance: Optional[float] = None
    notes: Optional[str] = None


class MortgageLoanUpdate(BaseModel):
    asset_id: Optional[int] = None
    lender: Optional[str] = None
    loan_number: Optional[str] = None
    original_amount: Optional[float] = None
    interest_rate: Optional[float] = None
    term_months: Optional[int] = None
    monthly_payment: Optional[float] = None
    start_date: Optional[str] = None
    current_balance: Optional[float] = None
    notes: Optional[str] = None


class MortgageLoanOut(BaseModel):
    id: int
    user_id: int
    asset_id: int
    lender: str
    loan_number: Optional[str]
    original_amount: Optional[float]
    interest_rate: Optional[float]
    term_months: Optional[int]
    monthly_payment: Optional[float]
    start_date: Optional[str]
    current_balance: Optional[float]
    document_url: Optional[str]
    document_filename: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Property valuations
# ---------------------------------------------------------------------------

class PropertyValuationCreate(BaseModel):
    asset_id: int
    valuation_amount: float
    valuation_date: Optional[str] = None
    source: Optional[str] = None
    notes: Optional[str] = None


class PropertyValuationUpdate(BaseModel):
    asset_id: Optional[int] = None
    valuation_amount: Optional[float] = None
    valuation_date: Optional[str] = None
    source: Optional[str] = None
    notes: Optional[str] = None


class PropertyValuationOut(BaseModel):
    id: int
    user_id: int
    asset_id: int
    valuation_amount: float
    valuation_date: Optional[str]
    source: Optional[str]
    document_url: Optional[str]
    document_filename: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Property tax records
# ---------------------------------------------------------------------------

class PropertyTaxRecordCreate(BaseModel):
    asset_id: int
    tax_year: int
    assessed_value: Optional[float] = None
    tax_amount: Optional[float] = None
    due_date: Optional[str] = None
    paid: bool = False
    notes: Optional[str] = None


class PropertyTaxRecordUpdate(BaseModel):
    asset_id: Optional[int] = None
    tax_year: Optional[int] = None
    assessed_value: Optional[float] = None
    tax_amount: Optional[float] = None
    due_date: Optional[str] = None
    paid: Optional[bool] = None
    notes: Optional[str] = None


class PropertyTaxRecordOut(BaseModel):
    id: int
    user_id: int
    asset_id: int
    tax_year: int
    assessed_value: Optional[float]
    tax_amount: Optional[float]
    due_date: Optional[str]
    paid: bool
    document_url: Optional[str]
    document_filename: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

class RealEstateSummary(BaseModel):
    property_count: int
    total_mortgage_balance: float
    total_valuation: float
    estimated_equity: float
    taxes_due_soon: int  # within 60 days
