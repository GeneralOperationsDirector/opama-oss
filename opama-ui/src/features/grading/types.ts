export interface CenteringResult {
  left_pct: number;
  right_pct: number;
  top_pct: number;
  bottom_pct: number;
  lr_ratio: string;
  tb_ratio: string;
  score: number;
}

export interface CornerResult {
  top_left: number;
  top_right: number;
  bottom_left: number;
  bottom_right: number;
  score: number;
}

export interface SurfaceResult {
  texture_score: number;
  scratch_risk: number;
  score: number;
  flags: string[];
  symmetry: number;
  th_h_mean: number;
  th_v_mean: number;
}

export interface EdgeResult {
  top_std: number;
  bottom_std: number;
  left_std: number;
  right_std: number;
  score: number;
}

export interface CardIdentification {
  name: string | null;
  number: string | null;
  set_name: string | null;
  catalog_card_id: string | null;
  catalog_set_id: string | null;
  catalog_match: boolean;
  confidence: "high" | "medium" | "low";
}

export interface GradeResult {
  id?: number;
  estimated_grade: number;
  grade_label: string;
  confidence: "low" | "medium" | "high";
  centering: CenteringResult;
  corners: CornerResult;
  surface: SurfaceResult;
  edges: EdgeResult;
  notes: string[];
  identification: CardIdentification | null;
  transferred_to: string | null;
  transferred_item_id: number | null;
  analyzed_at?: string;
}

export interface TransferIn {
  destination: "inventory" | "asset";
  card_id?: string | null;
  card_name?: string | null;
  card_number?: string | null;
  condition?: string | null;
  quantity: number;
  purchase_price?: number | null;
  grading_company?: string | null;
  actual_grade?: number | null;
  estimated_value?: number | null;
  notes?: string | null;
}

export interface TransferOut {
  destination: string;
  item_id: number;
  card_id: string | null;
  message: string;
}

export type Verdict = "too_low" | "accurate" | "too_high";
export type Dimension = "centering" | "corners" | "surface" | "edges";

export interface FeedbackIn {
  overall_verdict: Verdict;
  actual_grade?: number | null;
  grading_company?: string | null;
  inaccurate_dimensions: Dimension[];
  notes?: string | null;
}

export interface FeedbackOut extends FeedbackIn {
  id: number;
  grade_result_id: number;
  submitted_at: string;
}

export interface DimensionAccuracy {
  dimension: string;
  times_flagged: number;
  flag_rate: number;
}

export interface ProviderStats {
  provider: string;
  total_attempts: number;
  name_evaluated: number;
  name_accuracy: number | null;
  number_evaluated: number;
  number_accuracy: number | null;
}

export interface FeedbackStats {
  total_analyses: number;
  total_feedback: number;
  feedback_rate: number;
  accurate_pct: number;
  too_high_pct: number;
  too_low_pct: number;
  graded_count: number;
  mean_error: number | null;
  mean_abs_error: number | null;
  dimension_accuracy: DimensionAccuracy[];
}
