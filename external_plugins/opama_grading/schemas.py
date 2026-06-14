from typing import Literal, Optional
from pydantic import BaseModel, Field


class CenteringOut(BaseModel):
    left_pct: float
    right_pct: float
    top_pct: float
    bottom_pct: float
    lr_ratio: str      # e.g. "55/45"
    tb_ratio: str      # e.g. "52/48"
    score: int         # 1–10


class CornerOut(BaseModel):
    top_left: float    # 0–100 sharpness
    top_right: float
    bottom_left: float
    bottom_right: float
    score: int         # 1–10


class SurfaceOut(BaseModel):
    texture_score: float    # raw Laplacian variance
    scratch_risk: float     # 0–1
    score: int              # 1–10
    flags: list[str]
    symmetry: float = 0.0
    th_h_mean: float = 0.0
    th_v_mean: float = 0.0


class EdgeOut(BaseModel):
    top_std: float = 0.0
    bottom_std: float = 0.0
    left_std: float = 0.0
    right_std: float = 0.0
    score: int


class CardIdentificationOut(BaseModel):
    name: Optional[str] = None
    number: Optional[str] = None          # as printed, e.g. "049/091"
    set_name: Optional[str] = None
    catalog_card_id: Optional[str] = None # matched Card.id in catalog
    catalog_set_id: Optional[str] = None
    catalog_match: bool = False
    confidence: str = "low"              # "high"|"medium"|"low"


class GradeResultOut(BaseModel):
    id: Optional[int] = None
    estimated_grade: float
    grade_label: str
    confidence: str
    centering: CenteringOut
    corners: CornerOut
    surface: SurfaceOut
    edges: EdgeOut
    notes: list[str]
    identification: Optional[CardIdentificationOut] = None
    transferred_to: Optional[str] = None
    transferred_item_id: Optional[int] = None
    analyzed_at: Optional[str] = None


class RecenterIn(BaseModel):
    border_r: int = Field(ge=0, le=255)
    border_g: int = Field(ge=0, le=255)
    border_b: int = Field(ge=0, le=255)


class RecenterOut(BaseModel):
    centering: CenteringOut
    estimated_grade: float
    grade_label: str
    method: str   # "color_hint" | "gradient_fallback"


class TransferIn(BaseModel):
    destination: Literal["inventory", "asset"]

    # User-confirmed (possibly corrected) card identity
    card_id: Optional[str] = None           # catalog Card.id — required for inventory
    card_name: Optional[str] = None         # display name for asset fallback
    card_number: Optional[str] = None       # for reference only

    # Common fields
    condition: Optional[str] = None         # "NM"|"LP"|"MP"|"HP"|"DMG"
    quantity: int = Field(default=1, ge=1)
    purchase_price: Optional[float] = None

    # Grading company override (if user knows the actual grader)
    grading_company: Optional[str] = None   # "PSA"|"CGC"|"BGS"|"SGC"
    actual_grade: Optional[float] = Field(default=None, ge=1, le=10)

    # Asset-only fields
    estimated_value: Optional[float] = None
    notes: Optional[str] = None


class TransferOut(BaseModel):
    destination: str         # "inventory" | "asset"
    item_id: int
    card_id: Optional[str] = None
    message: str


Verdict = Literal["too_low", "accurate", "too_high"]
Dimension = Literal["centering", "corners", "surface", "edges"]


class FeedbackIn(BaseModel):
    overall_verdict: Verdict
    actual_grade: Optional[float] = Field(default=None, ge=1, le=10)
    grading_company: Optional[str] = None   # "PSA" | "CGC" | "BGS" | "SGC"
    inaccurate_dimensions: list[Dimension] = Field(default_factory=list)
    notes: Optional[str] = Field(default=None, max_length=500)


class FeedbackOut(BaseModel):
    id: int
    grade_result_id: int
    overall_verdict: Verdict
    actual_grade: Optional[float]
    grading_company: Optional[str]
    inaccurate_dimensions: list[str]
    notes: Optional[str]
    submitted_at: str


class DimensionAccuracy(BaseModel):
    dimension: str
    times_flagged: int          # how often users marked this dimension wrong
    flag_rate: float            # fraction of feedback submissions that flagged it


class ProviderStatsOut(BaseModel):
    provider: str
    total_attempts: int
    name_evaluated: int           # attempts where ground truth is known
    name_accuracy: Optional[float]  # fraction correct (None if no evaluations yet)
    number_evaluated: int
    number_accuracy: Optional[float]


class FeedbackStats(BaseModel):
    total_analyses: int         # all CardGradeResult rows for this user
    total_feedback: int         # how many have received feedback
    feedback_rate: float        # fraction of analyses that got feedback
    accurate_pct: float         # % of feedback where verdict == "accurate"
    too_high_pct: float
    too_low_pct: float
    # When actual grades are known
    graded_count: int           # submissions with a real slab grade
    mean_error: Optional[float] # avg (estimated - actual); positive = we over-grade
    mean_abs_error: Optional[float]
    dimension_accuracy: list[DimensionAccuracy]
