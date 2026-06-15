"""
Property Records — SQLModel tables.

Three tables, each linked to a specific CustomAsset (a property the user
owns via the "Real Estate" collection template):

- MortgageLoan: a mortgage/loan against the property (lender, terms,
  user-maintained current balance, document).
- PropertyValuation: a point-in-time valuation (appraisal, market estimate,
  tax assessment, ...).
- PropertyTaxRecord: a property tax bill for a given tax year, with an
  optional due date and paid flag.

As with Vehicle Maintenance, every record belongs to exactly one property,
so asset_id is required. user_id is denormalized for O(1) ownership checks,
consistent with every other table in the codebase.
"""

from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field


class MortgageLoan(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    asset_id: int = Field(foreign_key="customasset.id", ondelete="CASCADE", index=True)

    lender: str
    loan_number: Optional[str] = None
    original_amount: Optional[float] = None
    interest_rate: Optional[float] = None  # percent, e.g. 6.25
    term_months: Optional[int] = None
    monthly_payment: Optional[float] = None
    start_date: Optional[str] = None  # ISO date YYYY-MM-DD
    current_balance: Optional[float] = None  # user-maintained

    document_url: Optional[str] = None
    document_filename: Optional[str] = None
    notes: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class PropertyValuation(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    asset_id: int = Field(foreign_key="customasset.id", ondelete="CASCADE", index=True)

    valuation_amount: float
    valuation_date: Optional[str] = None  # ISO date YYYY-MM-DD
    source: Optional[str] = None  # e.g. "Appraisal", "Market Estimate", "Tax Assessment"

    document_url: Optional[str] = None
    document_filename: Optional[str] = None
    notes: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class PropertyTaxRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    asset_id: int = Field(foreign_key="customasset.id", ondelete="CASCADE", index=True)

    tax_year: int
    assessed_value: Optional[float] = None
    tax_amount: Optional[float] = None
    due_date: Optional[str] = None  # ISO date — used for "due soon"
    paid: bool = Field(default=False)

    document_url: Optional[str] = None
    document_filename: Optional[str] = None
    notes: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
