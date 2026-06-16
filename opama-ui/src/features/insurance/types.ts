// Types mirroring services/insurance/schemas.py response shapes.

export interface PolicyItem {
  id: number;
  policy_id: number;
  asset_id: number | null;
  appraisal_id: number | null;
  description: string;
  scheduled_amount: number | null;
}

export interface InsurancePolicy {
  id: number;
  user_id: number;
  provider: string;
  policy_number: string | null;
  policy_type: string | null;
  coverage_amount: number | null;
  deductible: number | null;
  premium_amount: number | null;
  premium_frequency: string | null;
  start_date: string | null;
  end_date: string | null;
  document_url: string | null;
  document_filename: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface InsurancePolicyDetail extends InsurancePolicy {
  items: PolicyItem[];
}

export interface Appraisal {
  id: number;
  user_id: number;
  asset_id: number | null;
  appraiser_name: string | null;
  appraised_value: number;
  appraisal_date: string | null;
  document_url: string | null;
  document_filename: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface InsuranceSummary {
  policy_count: number;
  appraisal_count: number;
  total_coverage: number;
  total_scheduled: number;
  policies_expiring_soon: number;
}

// Payload shapes for create/update requests (subset of fields, all optional on update).
export type InsurancePolicyForm = Omit<InsurancePolicy, "id" | "user_id" | "document_url" | "document_filename" | "created_at" | "updated_at">;

export type AppraisalForm = Omit<Appraisal, "id" | "user_id" | "document_url" | "document_filename" | "created_at" | "updated_at">;

export type PolicyItemForm = Omit<PolicyItem, "id" | "policy_id">;
