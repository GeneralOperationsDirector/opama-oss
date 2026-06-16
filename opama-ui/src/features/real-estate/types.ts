// Types mirroring services/real_estate/schemas.py response shapes.

export interface MortgageLoan {
  id: number;
  user_id: number;
  asset_id: number;
  lender: string;
  loan_number: string | null;
  original_amount: number | null;
  interest_rate: number | null;
  term_months: number | null;
  monthly_payment: number | null;
  start_date: string | null;
  current_balance: number | null;
  document_url: string | null;
  document_filename: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface PropertyValuation {
  id: number;
  user_id: number;
  asset_id: number;
  valuation_amount: number;
  valuation_date: string | null;
  source: string | null;
  document_url: string | null;
  document_filename: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface PropertyTaxRecord {
  id: number;
  user_id: number;
  asset_id: number;
  tax_year: number;
  assessed_value: number | null;
  tax_amount: number | null;
  due_date: string | null;
  paid: boolean;
  document_url: string | null;
  document_filename: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface RealEstateSummary {
  property_count: number;
  total_mortgage_balance: number;
  total_valuation: number;
  estimated_equity: number;
  taxes_due_soon: number;
}

// Payload shapes for create/update requests.
export type MortgageLoanForm = Omit<MortgageLoan, "id" | "user_id" | "document_url" | "document_filename" | "created_at" | "updated_at">;

export type PropertyValuationForm = Omit<PropertyValuation, "id" | "user_id" | "document_url" | "document_filename" | "created_at" | "updated_at">;

export type PropertyTaxRecordForm = Omit<PropertyTaxRecord, "id" | "user_id" | "document_url" | "document_filename" | "created_at" | "updated_at">;
