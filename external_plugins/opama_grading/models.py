from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field


class CardGradeResult(SQLModel, table=True):
    """
    Stored result of a card grading analysis.
    Optionally linked to an inventory item or custom asset.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)

    # Optional links to existing records. card_id/inventory_item_id are soft
    # references (no DB-level FK) since `card`/`inventoryitem` live in the
    # optional opama_pokemon_tcg external plugin and may not exist in this
    # deployment's schema. asset_id keeps its FK since custom_assets is core.
    card_id: Optional[str] = Field(default=None, index=True)
    inventory_item_id: Optional[int] = Field(default=None, index=True)
    asset_id: Optional[int] = Field(default=None, foreign_key="customasset.id")

    # Top-level verdict
    estimated_grade: float        # e.g. 8.5
    grade_label: str              # "Gem Mint", "Mint", "NM-MT", etc.
    confidence: str               # "low" | "medium" | "high"

    # Centering (percentage of total border on each side)
    centering_left_pct: float
    centering_right_pct: float
    centering_top_pct: float
    centering_bottom_pct: float
    centering_score: int          # 1–10

    # Corners (0–100 sharpness per corner, 10-scale overall)
    corner_tl: float
    corner_tr: float
    corner_bl: float
    corner_br: float
    corner_score: int             # 1–10

    # Surface
    surface_score: int            # 1–10
    surface_scratch_risk: float   # 0–1
    surface_texture_score: Optional[float] = None  # raw Laplacian variance

    # Edges
    edge_score: int               # 1–10
    edge_top_std: Optional[float] = None
    edge_bottom_std: Optional[float] = None
    edge_left_std: Optional[float] = None
    edge_right_std: Optional[float] = None
    surface_symmetry: Optional[float] = None
    surface_th_h: Optional[float] = None
    surface_th_v: Optional[float] = None

    # Human-readable observations (JSON array stored as text)
    notes: Optional[str] = None

    # Card identification (populated from Claude Vision + catalog lookup)
    identified_name: Optional[str] = None
    identified_number: Optional[str] = None      # as printed, e.g. "049/091"
    identified_set_name: Optional[str] = None
    identified_catalog_card_id: Optional[str] = None  # matched Card.id
    identified_catalog_set_id: Optional[str] = None
    identification_confidence: Optional[str] = None   # "high"|"medium"|"low"|None

    # Transfer tracking
    transferred_to: Optional[str] = None         # "inventory" | "asset"
    transferred_item_id: Optional[int] = None

    # Guide rectangles used during analysis ("x,y,w,h" in original image pixels)
    guide_outer: Optional[str] = None
    guide_inner: Optional[str] = None

    analyzed_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class IdentificationAttempt(SQLModel, table=True):
    """
    One row per provider per grading analysis.

    Stores what each extraction strategy (Ollama full-image, Ollama region-crop,
    Tesseract) actually read from the card. When the user corrects the
    identification during the transfer step, `actual_*` fields and `*_correct`
    flags are filled in — creating the ground-truth labels used by provider stats.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    grade_result_id: int = Field(foreign_key="cardgraderesult.id", index=True)

    provider: str                           # e.g. "ollama_full:llama3.2-vision"

    # What this provider extracted
    extracted_name: Optional[str] = None
    extracted_number: Optional[str] = None  # e.g. "049/091"
    extracted_set: Optional[str] = None

    # Ground truth — filled when user confirms or corrects during transfer
    actual_name: Optional[str] = None
    actual_number: Optional[str] = None
    actual_card_id: Optional[str] = None    # matched Card.id

    # Accuracy flags (None = not yet evaluated)
    name_correct: Optional[bool] = None
    number_correct: Optional[bool] = None

    attempted_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class GradeFeedback(SQLModel, table=True):
    """
    Human correction attached to a CardGradeResult.

    Captures whether the algorithm's estimate was right, which dimensions
    were wrong, and the actual grade if the card has been professionally graded.
    Rows accumulate over time to reveal systematic bias in the analyzer.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    grade_result_id: int = Field(foreign_key="cardgraderesult.id", index=True)
    user_id: int = Field(index=True)

    # Overall verdict
    overall_verdict: str  # "too_low" | "accurate" | "too_high"

    # Ground-truth grade (populated when user has a real slab)
    actual_grade: Optional[float] = None       # e.g. 9.0
    grading_company: Optional[str] = None      # "PSA" | "CGC" | "BGS" | "SGC"

    # Which dimensions were called out as wrong (JSON array of strings)
    # Possible values: "centering" | "corners" | "surface" | "edges"
    inaccurate_dimensions: Optional[str] = Field(default=None)

    notes: Optional[str] = None

    submitted_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
