"""
Card grading analysis using OpenCV.

Pipeline:
  1. Load image bytes → BGR array
  2. Detect card boundary and perspective-correct (rectify) to a standard size
  3. Measure centering — pixel distance from each card edge to inner printed border
  4. Analyze corners — Sobel gradient quality at each corner tip
  5. Analyze surface — directional scratch detection (distinguishes scratches from holo)
  6. Score each dimension against PSA-equivalent rubric → final grade estimate

Rectification strategies (tried in order):
  a. Standard Canny               — good contrast on any background
  b. Saturation mask              — colored card on white flatbed background
  c. Inverted brightness          — finds non-white regions
  d. Dark-region threshold        — card shadows/text on white background
  e. Adaptive threshold           — low-contrast cards
  f. Loose Canny                  — minimal contrast fallback
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

# Rectified card size in pixels (standard 63.5 × 88.9 mm aspect ratio)
_W = 630
_H = 882

# Fraction of each dimension to search for the inner printed border
_BORDER_SEARCH = 0.22


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CenteringResult:
    left_pct: float
    right_pct: float
    top_pct: float
    bottom_pct: float
    lr_ratio: str
    tb_ratio: str
    score: int


@dataclass
class CornerResult:
    top_left: float
    top_right: float
    bottom_left: float
    bottom_right: float
    score: int


@dataclass
class SurfaceResult:
    texture_score: float
    scratch_risk: float
    score: int
    flags: list[str] = field(default_factory=list)
    symmetry: float = 0.0
    th_h_mean: float = 0.0
    th_v_mean: float = 0.0


@dataclass
class EdgeResult:
    top_std: float
    bottom_std: float
    left_std: float
    right_std: float
    score: int


@dataclass
class GradeReport:
    estimated_grade: float
    grade_label: str
    confidence: str
    centering: CenteringResult
    corners: CornerResult
    surface: SurfaceResult
    edges: EdgeResult
    notes: list[str]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def analyze_card(image_bytes: bytes) -> GradeReport:
    """Analyze a card scan and return a GradeReport."""
    return analyze_card_guided(image_bytes)


# ---------------------------------------------------------------------------
# Step 1: Rectification
# ---------------------------------------------------------------------------

def _order_points(pts: np.ndarray) -> np.ndarray:
    """Order 4 corner points as TL, TR, BR, BL."""
    rect = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    d = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(d)]
    rect[3] = pts[np.argmax(d)]
    return rect


def _saturation_edges(img: np.ndarray) -> np.ndarray:
    """
    Build an edge map that captures the FULL CARD outline, not just its artwork.

    Previous approach: small morphological close on the sat+dark mask.
    Problem: the closure range (~30 px) was narrower than the card's white border
    (~40–80 px depending on scan DPI), so the detected contour wrapped the
    artwork window rather than the full card — causing the perspective warp to
    zoom into the artwork and miss the actual card boundary.

    New approach:
      1. Detect all coloured + dark content (artwork, text, coloured card frame).
      2. Compute the convex hull of that content — the outer envelope of every
         non-white element on the card.
      3. Dilate the hull outward by ~7% of the hull's shorter side.  This is
         resolution-agnostic: the white border is ~5.5% of card width and the
         hull covers ~85% of the card, so 7% × hull ≈ 6% of card ≈ border width.
      4. Zero the outermost image rows/cols so Canny always produces a closed
         ring (the ring would break if the mask touched the image boundary).
    """
    h, w = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]

    _, sat_mask  = cv2.threshold(sat, 20,  255, cv2.THRESH_BINARY)
    _, dark_mask = cv2.threshold(val, 220, 255, cv2.THRESH_BINARY_INV)
    combined = cv2.bitwise_or(sat_mask, dark_mask)

    # Remove isolated noise before computing hull
    noise_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    cleaned  = cv2.morphologyEx(combined, cv2.MORPH_OPEN, noise_k)

    contours, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        # Nothing detected — fall back to the original small-close approach
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
        filled = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel, iterations=2)
        return cv2.Canny(cv2.GaussianBlur(filled, (5, 5), 0), 50, 150)

    # Convex hull of every detected content point
    all_pts   = np.vstack(contours)
    hull      = cv2.convexHull(all_pts)

    # Hull-relative expansion: white border ≈ 5.5% of card width; hull covers
    # ~85% of card, so border = ~6.5% of hull width → 7% gives a small margin.
    bx, by, bw_hull, bh_hull = cv2.boundingRect(hull)
    pad = max(int(min(bw_hull, bh_hull) * 0.07), 15)

    hull_mask = np.zeros((h, w), np.uint8)
    cv2.fillConvexPoly(hull_mask, hull, 255)

    border_k = cv2.getStructuringElement(cv2.MORPH_RECT, (pad * 2 + 1, pad * 2 + 1))
    expanded = cv2.dilate(hull_mask, border_k)

    # Zero the image border so Canny produces a closed ring rather than edges
    # that end abruptly at the frame — open edges cause contour detection to
    # find only tiny fragments instead of the full card boundary.
    expanded[:3, :] = 0
    expanded[-3:, :] = 0
    expanded[:, :3] = 0
    expanded[:, -3:] = 0

    return cv2.Canny(cv2.GaussianBlur(expanded, (5, 5), 0), 50, 150)


def _background_sub_edges(img: np.ndarray) -> np.ndarray:
    """
    Estimate background colour from the image corners, then threshold pixels
    that differ significantly from it to isolate the card as foreground.

    Works for any card colour on any reasonably uniform background (dark table,
    coloured mat, scanner lid).  Complements _saturation_edges which targets
    flatbed scans; this one targets camera photos.
    """
    h, w = img.shape[:2]
    m = max(int(min(h, w) * 0.05), 10)

    corners = np.vstack([
        img[:m,   :m  ].reshape(-1, 3),
        img[:m,   w-m:].reshape(-1, 3),
        img[h-m:, :m  ].reshape(-1, 3),
        img[h-m:, w-m:].reshape(-1, 3),
    ]).astype(np.float32)
    bg = np.median(corners, axis=0)

    # Max per-channel distance from the estimated background colour
    diff = np.abs(img.astype(np.float32) - bg).max(axis=2).astype(np.uint8)
    _, fg = cv2.threshold(diff, 18, 255, cv2.THRESH_BINARY)

    # Close to fill the card body (including white border areas on coloured bgs)
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25))
    filled = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, k, iterations=3)

    return cv2.Canny(cv2.GaussianBlur(filled, (5, 5), 0), 50, 150)


def _try_warp(img: np.ndarray, edges: np.ndarray, dilation: int = 2) -> Optional[np.ndarray]:
    """
    Try to find a card-shaped quadrilateral in the edge map and warp to
    standard size.  Returns None if no suitable contour is found.

    Two quadrilateral fitting strategies per contour:
      1. approxPolyDP — clean when edges form a crisp rectangle
      2. minAreaRect  — fallback for slightly-rotated cards where polygon
         approximation produces 5+ corners instead of exactly 4
    """
    kernel = np.ones((3, 3), np.uint8)
    dilated = cv2.dilate(edges, kernel, iterations=dilation)

    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)

    img_area = img.shape[0] * img.shape[1]

    for cnt in contours[:10]:
        area = cv2.contourArea(cnt)
        # 0.97 upper bound: allow cards that nearly fill the frame (close-up shots)
        if area < img_area * 0.05 or area > img_area * 0.97:
            continue

        peri   = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)

        if len(approx) == 4:
            pts  = approx.reshape(4, 2).astype(np.float32)
            rect = _order_points(pts)
        else:
            # minAreaRect handles rotated cards and imperfect polygon approximations
            box    = cv2.minAreaRect(cnt)
            bw, bh = box[1]
            if bh < 1 or bw < 1:
                continue
            short, long_ = sorted([bw, bh])
            if not (0.55 < short / long_ < 0.85):
                continue
            pts  = cv2.boxPoints(box).astype(np.float32)
            rect = _order_points(pts)

        w_px = float(np.linalg.norm(rect[1] - rect[0]))
        h_px = float(np.linalg.norm(rect[3] - rect[0]))
        if h_px < 1:
            continue

        aspect = w_px / h_px
        if not (0.55 < aspect < 0.85):
            continue

        dst = np.array([[0, 0], [_W - 1, 0], [_W - 1, _H - 1], [0, _H - 1]],
                       dtype=np.float32)
        M = cv2.getPerspectiveTransform(rect, dst)
        return cv2.warpPerspective(img, M, (_W, _H)), rect

    return None


_STRATEGY_NAMES = [
    "Canny (standard)",
    "Background subtraction",
    "Saturation + hull",
    "Inverted brightness",
    "Dark region",
    "Adaptive threshold",
    "Morphological close",
    "Loose Canny",
]


def _rectify(img: np.ndarray) -> tuple[np.ndarray, int, str, Optional[np.ndarray]]:
    """
    Try eight edge-detection strategies in order of expected reliability.
    Returns (rectified_image, confidence_pts, strategy_name, src_quad).
    confidence_pts: 4 = primary strategy succeeded, 2 = fallback strategy,
                    0 = resize fallback (no boundary detected)
    src_quad: 4×2 float32 array of detected card corners, or None on resize fallback.
    """
    gray    = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # g. Morphological close on adaptive threshold — bridges broken boundaries
    #    in camera photos where the card edge is interrupted by shadows or blur
    _adapt = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY_INV, 21, 5)
    _kclose = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25))
    _closed = cv2.morphologyEx(_adapt, cv2.MORPH_CLOSE, _kclose)

    strategies = [
        # a. Standard Canny — baseline, works when card contrasts with background
        cv2.Canny(blurred, 50, 150),
        # b. Background subtraction (corner-sampled) — best for camera photos on
        #    any uniform surface; finds full card regardless of border colour
        _background_sub_edges(img),
        # c. Saturation + convex-hull expansion — best for flatbed scans; detects
        #    all card content then dilates outward to include the white border
        _saturation_edges(img),
        # d. Inverted brightness — finds non-white areas including card on white bed
        cv2.threshold(gray, 235, 255, cv2.THRESH_BINARY_INV)[1],
        # e. Dark-region only — catches cards where only text/borders show contrast
        cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY_INV)[1],
        # f. Adaptive threshold — handles uneven illumination across the scan
        _adapt,
        # g. Morphological close of adaptive threshold — bridges gaps in card boundary
        _closed,
        # h. Loose Canny — last resort for very low contrast
        cv2.Canny(blurred, 20, 80),
    ]

    for i, edges in enumerate(strategies):
        result = _try_warp(img, edges)
        if result is not None:
            warped, src_quad = result
            conf = 4 if i < 5 else 2
            return warped, conf, _STRATEGY_NAMES[i], src_quad

    # Last resort: heavy dilation to connect any surviving boundary fragments
    for edges in [cv2.Canny(blurred, 30, 100), _saturation_edges(img)]:
        result = _try_warp(img, edges, dilation=5)
        if result is not None:
            warped, src_quad = result
            return warped, 2, "Heavy dilation", src_quad

    # Fallback: assume image is already a tight card crop, just resize
    return cv2.resize(img, (_W, _H)), 0, "Resize fallback", None


# ---------------------------------------------------------------------------
# Step 2: Centering
# ---------------------------------------------------------------------------

def _find_inner_border(signal: np.ndarray, search_px: int, from_end: bool = False) -> int:
    """
    Find the strongest gradient in the first `search_px` pixels of a 1-D intensity
    signal.  Skips the first 10% to avoid picking up the image boundary itself.
    """
    if from_end:
        signal = signal[::-1]

    segment = signal[:search_px].astype(np.float32)
    grad    = np.abs(np.gradient(segment))

    skip = max(int(search_px * 0.10), 4)
    grad[:skip] = 0

    if grad.max() < 3:
        return search_px // 3

    return int(np.argmax(grad))


def _measure_centering(rect: np.ndarray) -> CenteringResult:
    h, w = rect.shape[:2]
    gray = cv2.cvtColor(rect, cv2.COLOR_BGR2GRAY)

    sw   = max(int(w * _BORDER_SEARCH), 40)
    sh   = max(int(h * _BORDER_SEARCH), 56)
    band = 12

    mid_y = h // 2
    h_row = gray[mid_y - band : mid_y + band, :].mean(axis=0)
    mid_x = w // 2
    v_col = gray[:, mid_x - band : mid_x + band].mean(axis=1)

    left_px   = float(_find_inner_border(h_row, sw))
    right_px  = float(_find_inner_border(h_row, sw, from_end=True))
    top_px    = float(_find_inner_border(v_col, sh))
    bottom_px = float(_find_inner_border(v_col, sh, from_end=True))

    total_h = left_px + right_px
    total_v = top_px + bottom_px

    left_pct  = round(left_px  / total_h * 100, 1) if total_h >= 4 else 50.0
    right_pct = round(100 - left_pct, 1)            if total_h >= 4 else 50.0
    top_pct   = round(top_px   / total_v * 100, 1) if total_v >= 4 else 50.0
    bottom_pct = round(100 - top_pct, 1)            if total_v >= 4 else 50.0

    # `worse` = the larger border percentage on the more off-center axis.
    # 50 = perfectly centered (50/50); higher = more lopsided. The rubric maps
    # the offset to a 1–10 PSA-style grade: ≤55 (i.e. up to 55/45) is gem-mint
    # centering, each +5% off drops one grade. Mirrored in
    # _centering_score_from_pcts below — keep the two tables in sync.
    worse = max(left_pct, right_pct, top_pct, bottom_pct)

    if   worse <= 55: score = 10
    elif worse <= 60: score = 9
    elif worse <= 65: score = 8
    elif worse <= 70: score = 7
    elif worse <= 75: score = 6
    elif worse <= 80: score = 5
    elif worse <= 85: score = 4
    elif worse <= 90: score = 3
    elif worse <= 95: score = 2
    else:             score = 1

    return CenteringResult(
        left_pct=left_pct,   right_pct=right_pct,
        top_pct=top_pct,     bottom_pct=bottom_pct,
        lr_ratio=f"{round(left_pct)}/{round(right_pct)}",
        tb_ratio=f"{round(top_pct)}/{round(bottom_pct)}",
        score=score,
    )


# ---------------------------------------------------------------------------
# Step 2b: Color-hint centering (user-supplied border colour)
# ---------------------------------------------------------------------------

def _centering_score_from_pcts(left_pct: float, right_pct: float,
                                top_pct: float, bottom_pct: float) -> int:
    worse = max(left_pct, right_pct, top_pct, bottom_pct)
    if   worse <= 55: return 10
    elif worse <= 60: return 9
    elif worse <= 65: return 8
    elif worse <= 70: return 7
    elif worse <= 75: return 6
    elif worse <= 80: return 5
    elif worse <= 85: return 4
    elif worse <= 90: return 3
    elif worse <= 95: return 2
    else:             return 1


def _guided_find_border(signal: np.ndarray, hint: float) -> float:
    """
    Find the inner border near a hint position in a 1-D intensity signal.
    Searches a ±15% window around the hint; falls back to the hint when no
    clear gradient is found so the projected guide acts as the final answer.
    Pass the signal reversed when searching from the far end.
    """
    hint_i = int(round(hint))
    window = max(int(max(hint, 1.0) * 0.15), 8)
    lo = max(4, hint_i - window)
    hi = min(len(signal), hint_i + window + 1)
    if hi <= lo:
        return hint
    seg = signal[lo:hi].astype(np.float32)
    grad = np.abs(np.gradient(seg))
    if grad.max() < 3:
        return hint
    return float(lo + int(np.argmax(grad)))


def _measure_centering_guided(
    rect: np.ndarray,
    hint_left: float,
    hint_right: float,
    hint_top: float,
    hint_bottom: float,
) -> CenteringResult:
    """
    Gradient-based border detection seeded by guide positions already projected
    into the rectified image's coordinate space.  Searches a ±15% window around
    each hint; falls back to the hint coordinate when no clear gradient is found.
    """
    h, w = rect.shape[:2]
    gray = cv2.cvtColor(rect, cv2.COLOR_BGR2GRAY)
    band = 12

    mid_y = h // 2
    h_row = gray[mid_y - band : mid_y + band, :].mean(axis=0)
    mid_x = w // 2
    v_col = gray[:, mid_x - band : mid_x + band].mean(axis=1)

    left_px   = _guided_find_border(h_row,       hint_left)
    right_px  = _guided_find_border(h_row[::-1], hint_right)
    top_px    = _guided_find_border(v_col,       hint_top)
    bottom_px = _guided_find_border(v_col[::-1], hint_bottom)

    total_h = left_px + right_px
    total_v = top_px + bottom_px

    left_pct   = round(left_px  / total_h * 100, 1) if total_h >= 2 else 50.0
    right_pct  = round(100 - left_pct, 1)           if total_h >= 2 else 50.0
    top_pct    = round(top_px   / total_v * 100, 1) if total_v >= 2 else 50.0
    bottom_pct = round(100 - top_pct, 1)            if total_v >= 2 else 50.0

    return CenteringResult(
        left_pct=left_pct,   right_pct=right_pct,
        top_pct=top_pct,     bottom_pct=bottom_pct,
        lr_ratio=f"{round(left_pct)}/{round(right_pct)}",
        tb_ratio=f"{round(top_pct)}/{round(bottom_pct)}",
        score=_centering_score_from_pcts(left_pct, right_pct, top_pct, bottom_pct),
    )


def analyze_card_guided(
    image_bytes: bytes,
    outer_xywh: Optional[tuple[int, int, int, int]] = None,
    inner_xywh: Optional[tuple[int, int, int, int]] = None,
) -> GradeReport:
    """
    Full grading pipeline with optional user-supplied boundary guides.

    outer_xywh — rectangle around the full card edge in original image pixels.
      If provided, used directly as the perspective-warp source instead of
      auto-detected edges; gives a perfect crop even when background detection
      fails.

    inner_xywh — rectangle around the inner content area (artwork start) in
      original image pixels.  When both rectangles are supplied the inner
      guide is projected through the perspective transform into rectified
      space and used as a seed for the gradient-based border detector, giving
      it a precise search window instead of the default fixed 22% fraction.

    Falls back to the standard pipeline for any guide not provided.
    """
    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image — unsupported format or corrupted file")

    # --- Rectification ---
    if outer_xywh:
        ox, oy, ow, oh = outer_xywh
        src = np.float32([[ox, oy], [ox + ow, oy], [ox + ow, oy + oh], [ox, oy + oh]])
        dst = np.float32([[0, 0], [_W - 1, 0], [_W - 1, _H - 1], [0, _H - 1]])
        M   = cv2.getPerspectiveTransform(src, dst)
        rectified      = cv2.warpPerspective(img, M, (_W, _H))
        confidence_pts = 4

        # --- Centering (guided) ---
        if inner_xywh:
            # Project inner guide corners through M into rectified space so
            # border distances are measured in the corrected coordinate frame.
            ix, iy, iw, ih = inner_xywh
            inner_corners = np.float32([
                [ix,      iy],
                [ix + iw, iy],
                [ix + iw, iy + ih],
                [ix,      iy + ih],
            ]).reshape(1, -1, 2)
            wp = cv2.perspectiveTransform(inner_corners, M).reshape(-1, 2)
            hint_left   = max(0.0, float(wp[:, 0].min()))
            hint_right  = max(0.0, float(_W - wp[:, 0].max()))
            hint_top    = max(0.0, float(wp[:, 1].min()))
            hint_bottom = max(0.0, float(_H - wp[:, 1].max()))
            centering = _measure_centering_guided(
                rectified, hint_left, hint_right, hint_top, hint_bottom
            )
        else:
            centering = _measure_centering(rectified)
    else:
        rectified, confidence_pts, *_ = _rectify(img)
        centering = _measure_centering(rectified)

    corners = _analyze_corners(rectified)
    surface = _analyze_surface(rectified)
    edges   = _score_edges(rectified)

    grade, label = _compute_grade(centering, corners, surface, edges.score)
    confidence   = _confidence(confidence_pts)
    notes        = _build_notes(centering, corners, surface, edges.score)

    return GradeReport(
        estimated_grade=grade, grade_label=label, confidence=confidence,
        centering=centering, corners=corners, surface=surface,
        edges=edges, notes=notes,
    )


def measure_centering_color_hint(rect: np.ndarray, border_rgb: tuple[int, int, int]) -> CenteringResult:
    """
    Re-measure centering using a known border colour supplied by the user.

    Strategy:
      1. Convert the hint colour to HSV.
      2. Build a binary mask of pixels that match the border hue (±25°) with
         sufficient saturation — this isolates the coloured card frame band.
      3. For each of the four sides, scan inward along a 1-D column/row sum of
         the mask.  The first position where the coloured-band signal rises
         above a noise threshold is where the white outer border ends.
      4. If the colour is near-grey / near-white (saturation < 40), or detection
         fails on any side, fall back silently to the standard gradient method.

    Uses the same percentage and scoring rubric as _measure_centering so results
    are directly comparable.
    """
    h, w = rect.shape[:2]

    r, g, b = border_rgb
    sample_bgr = np.uint8([[[b, g, r]]])
    sample_hsv  = cv2.cvtColor(sample_bgr, cv2.COLOR_BGR2HSV)[0][0]
    hue = int(sample_hsv[0])
    sat = int(sample_hsv[1])

    # Low saturation → border is near-white/grey; gradient method is more reliable
    if sat < 40:
        return _measure_centering(rect)

    hsv = cv2.cvtColor(rect, cv2.COLOR_BGR2HSV)

    # Hue-wrap-aware range (OpenCV hue is 0–179)
    tol = 25
    lo1 = np.array([max(0, hue - tol),    30, 40])
    hi1 = np.array([min(179, hue + tol),  255, 255])

    if hue - tol < 0:
        # Wraps below 0 — add a second range from the high end
        lo2 = np.array([179 + (hue - tol), 30, 40])
        hi2 = np.array([179, 255, 255])
        mask = cv2.bitwise_or(cv2.inRange(hsv, lo1, hi1),
                              cv2.inRange(hsv, lo2, hi2))
    elif hue + tol > 179:
        lo2 = np.array([0, 30, 40])
        hi2 = np.array([(hue + tol) - 179, 255, 255])
        mask = cv2.bitwise_or(cv2.inRange(hsv, lo1, hi1),
                              cv2.inRange(hsv, lo2, hi2))
    else:
        mask = cv2.inRange(hsv, lo1, hi1)

    # Small open to suppress isolated noise pixels
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)

    sw = max(int(w * _BORDER_SEARCH), 40)
    sh = max(int(h * _BORDER_SEARCH), 56)

    def _find_rise(signal: np.ndarray, search_px: int) -> Optional[int]:
        """
        Find where the 1-D colour-presence signal first rises above noise.
        Returns None if the colour isn't convincingly present in the search zone.
        """
        seg = signal[:search_px].astype(np.float32)
        grad = np.gradient(seg)
        skip = max(int(search_px * 0.05), 2)
        grad[:skip] = 0
        if grad.max() < 1.0:
            return None
        return int(np.argmax(grad))

    # Column sums (how many coloured pixels per column) for L/R
    col_sums = mask.sum(axis=0).astype(float)
    # Row sums for T/B
    row_sums = mask.sum(axis=1).astype(float)

    left_px   = _find_rise(col_sums,        sw)
    right_px  = _find_rise(col_sums[::-1],  sw)
    top_px    = _find_rise(row_sums,        sh)
    bottom_px = _find_rise(row_sums[::-1],  sh)

    # Fall back to gradient method if colour wasn't found on any side
    if any(v is None for v in [left_px, right_px, top_px, bottom_px]):
        return _measure_centering(rect)

    total_h = left_px + right_px
    total_v = top_px + bottom_px

    left_pct   = round(left_px  / total_h * 100, 1) if total_h >= 4 else 50.0
    right_pct  = round(100 - left_pct, 1)            if total_h >= 4 else 50.0
    top_pct    = round(top_px   / total_v * 100, 1) if total_v >= 4 else 50.0
    bottom_pct = round(100 - top_pct, 1)             if total_v >= 4 else 50.0

    return CenteringResult(
        left_pct=left_pct,    right_pct=right_pct,
        top_pct=top_pct,      bottom_pct=bottom_pct,
        lr_ratio=f"{round(left_pct)}/{round(right_pct)}",
        tb_ratio=f"{round(top_pct)}/{round(bottom_pct)}",
        score=_centering_score_from_pcts(left_pct, right_pct, top_pct, bottom_pct),
    )


# ---------------------------------------------------------------------------
# Step 3: Corner analysis
# ---------------------------------------------------------------------------

def _corner_sharpness(patch: np.ndarray) -> float:
    """
    Measure corner quality using the 90th-percentile Sobel gradient magnitude.

    Why this beats Laplacian variance:
      - Laplacian variance measures overall texture complexity.  A white scanner
        background scores 0 (no texture), making it useless when rectification
        places background in the corner patch.  Complex artwork also inflates it.
      - Sobel 90th-percentile focuses on the *strongest edge* in the patch,
        ignoring background noise.  A sharp card corner has a crisp printed-border
        edge; a worn corner has a weak, diffuse transition.

    Returns 0–100 (higher = sharper / less wear).
    """
    gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY) if patch.ndim == 3 else patch

    # Upscale for finer edge resolution on the small patch
    up = cv2.resize(gray, (gray.shape[1] * 2, gray.shape[0] * 2),
                    interpolation=cv2.INTER_CUBIC)

    sx = cv2.Sobel(up.astype(np.float32), cv2.CV_32F, 1, 0, ksize=3)
    sy = cv2.Sobel(up.astype(np.float32), cv2.CV_32F, 0, 1, ksize=3)
    grad = np.sqrt(sx ** 2 + sy ** 2)

    # 90th percentile: robust to noise; captures the sharpest real edge
    p90 = float(np.percentile(grad, 90))

    # Scale: solid-colored card borders give p90 ~40–80 when undamaged;
    # artwork-heavy corners can reach ~150+. Cap at 100 to keep the scoring
    # meaningful across both card types.
    return float(round(min(p90 / 100.0 * 100, 100), 1))


def _analyze_corners(rect: np.ndarray) -> CornerResult:
    h, w = rect.shape[:2]
    cw = max(int(w * 0.10), 35)
    ch = max(int(h * 0.10), 48)

    tl = _corner_sharpness(rect[:ch,      :cw     ])
    tr = _corner_sharpness(rect[:ch,      w - cw: ])
    bl = _corner_sharpness(rect[h - ch:,  :cw     ])
    br = _corner_sharpness(rect[h - ch:,  w - cw: ])

    # Score driven by the two weakest corners
    vals     = sorted([tl, tr, bl, br])
    worst_avg = (vals[0] + vals[1]) / 2

    # 0–100 sharpness → 1–10 PSA-style score
    # Rubric calibrated against solid-colored borders (typical p90 range 40–90)
    if   worst_avg >= 75: score = 10
    elif worst_avg >= 60: score = 9
    elif worst_avg >= 45: score = 8
    elif worst_avg >= 32: score = 7
    elif worst_avg >= 22: score = 6
    elif worst_avg >= 14: score = 5
    elif worst_avg >=  8: score = 4
    else:                 score = max(1, round(worst_avg / 3))

    return CornerResult(top_left=tl, top_right=tr, bottom_left=bl, bottom_right=br,
                        score=score)


# ---------------------------------------------------------------------------
# Step 4: Surface analysis
# ---------------------------------------------------------------------------

def _analyze_surface(rect: np.ndarray) -> SurfaceResult:
    """
    Detect surface defects using directional morphological top-hat analysis.

    Key insight: holo/foil cards have bright linear features in BOTH horizontal
    and vertical directions (omnidirectional).  Real scratches from handling are
    predominantly UNIDIRECTIONAL.  By running top-hat in both axes and comparing,
    we can discount the risk for cards where the pattern is symmetric (holo) and
    preserve it for cards where one direction dominates (scratched).
    """
    h, w = rect.shape[:2]
    flags: list[str] = []

    # Work on the inner 70% of the card to exclude border effects
    mx = int(w * 0.15)
    my = int(h * 0.15)
    artwork = rect[my : h - my, mx : w - mx]
    gray    = cv2.cvtColor(artwork, cv2.COLOR_BGR2GRAY)

    # --- Texture score (kept for reference) ---
    lap          = cv2.Laplacian(gray, cv2.CV_64F)
    texture_score = round(float(lap.var()), 2)

    # --- Directional top-hat scratch detection ---
    k_h = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 1))  # horizontal lines
    k_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 25))  # vertical lines

    th_h = float(cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, k_h).mean())
    th_v = float(cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, k_v).mean())

    max_density = max(th_h, th_v, 0.001)
    min_density = min(th_h, th_v)

    # Symmetry ratio: 1.0 = equal both directions (holo), 0.0 = one direction only
    symmetry = min_density / max_density

    # Raw risk: scale the dominant direction
    raw_risk = max_density / 30.0

    # Holo discount: reduce risk proportionally to how symmetric the pattern is.
    # Foil/holo cards have equal energy both ways (symmetry ≈ 1.0) — discount up
    # to 85% so they don't false-positive as scratched.
    holo_discount = symmetry * 0.85
    scratch_risk  = round(float(min(raw_risk * (1.0 - holo_discount), 1.0)), 3)

    if scratch_risk > 0.55:
        flags.append("Surface scratches likely")
    elif scratch_risk > 0.35:
        flags.append("Minor surface wear possible")

    # NOTE: Horizontal banding / print line detection has been intentionally removed.
    # At consumer flatbed resolution (300–600 DPI), row-to-row brightness variation
    # is indistinguishable between three sources: genuine print line defects (rare,
    # require magnification to confirm), holo foil reflection patterns, and minor
    # scanner lamp non-uniformity.  Flagging it produces false positives on every
    # holo card.  It will be reintroduced when a frequency-domain approach capable
    # of distinguishing periodic print artifacts from foil texture is implemented.

    # Score — based solely on scratch risk so surface flags stay meaningful
    if   scratch_risk < 0.15 and not flags: score = 10
    elif scratch_risk < 0.25:               score = 9
    elif scratch_risk < 0.38:               score = 8
    elif scratch_risk < 0.50:               score = 7
    elif scratch_risk < 0.65:               score = 6
    elif scratch_risk < 0.80:               score = 5
    elif scratch_risk < 0.92:               score = 4
    else:                                   score = 3

    return SurfaceResult(
        texture_score=texture_score,
        scratch_risk=scratch_risk,
        score=score,
        flags=flags,
        symmetry=round(symmetry, 3),
        th_h_mean=round(th_h, 3),
        th_v_mean=round(th_v, 3),
    )


# ---------------------------------------------------------------------------
# Step 5: Edge scoring
# ---------------------------------------------------------------------------

def _score_edges(rect: np.ndarray) -> EdgeResult:
    """
    Assess edge straightness by pixel uniformity along each card edge strip.
    Chipped or worn edges introduce colour variation; clean edges are uniform.
    """
    h, w  = rect.shape[:2]
    gray  = cv2.cvtColor(rect, cv2.COLOR_BGR2GRAY)

    # Skip the outermost 3px: warpPerspective fills them with black (0) when the
    # card boundary doesn't perfectly align with the output frame, which inflates
    # std deviation and falsely triggers wear flags on clean cards.
    skip  = 3
    strip = 6

    top_std    = float(gray[skip : skip + strip,          skip : w - skip].std())
    bottom_std = float(gray[h - skip - strip : h - skip,  skip : w - skip].std())
    left_std   = float(gray[skip : h - skip,   skip : skip + strip        ].std())
    right_std  = float(gray[skip : h - skip,   w - skip - strip : w - skip].std())

    worst = max(top_std, bottom_std, left_std, right_std)

    if   worst < 10: score = 10
    elif worst < 18: score = 9
    elif worst < 28: score = 8
    elif worst < 40: score = 7
    elif worst < 55: score = 6
    elif worst < 70: score = 5
    elif worst < 90: score = 4
    elif worst < 110: score = 3
    else:             score = 2

    return EdgeResult(
        top_std=round(top_std, 2),
        bottom_std=round(bottom_std, 2),
        left_std=round(left_std, 2),
        right_std=round(right_std, 2),
        score=score,
    )


# ---------------------------------------------------------------------------
# Step 6: Grade computation
# ---------------------------------------------------------------------------

_LABELS = {
    10: "Gem Mint", 9: "Mint",    8: "NM-MT",     7: "Near Mint",
    6:  "EX-MT",    5: "Excellent", 4: "VG-EX",   3: "Very Good",
    2:  "Good",     1: "Poor",
}


def _compute_grade(c: CenteringResult, corners: CornerResult,
                   surface: SurfaceResult, edge: int) -> tuple[float, str]:
    # Edges excluded: gradient-border cards produce artificially high σ values.
    # Remaining weights renormalised: centering 40%, corners 40%, surface 20%.
    raw = (c.score * 0.40 + corners.score * 0.40 + surface.score * 0.20)
    grade     = max(1.0, min(10.0, round(raw * 2) / 2))
    label_key = min(_LABELS, key=lambda k: abs(k - grade))
    return grade, _LABELS[label_key]


def _confidence(contour_pts: int) -> str:
    return "high" if contour_pts == 4 else ("low" if contour_pts == 0 else "medium")


def _build_notes(c: CenteringResult, corners: CornerResult,
                 surface: SurfaceResult, edge: int) -> list[str]:
    notes: list[str] = []

    worse_lr = max(c.left_pct, c.right_pct)
    worse_tb = max(c.top_pct, c.bottom_pct)
    prefix   = "Off-center" if (worse_lr > 65 or worse_tb > 65) else "Centering"
    notes.append(f"{prefix}: L/R {c.lr_ratio}, T/B {c.tb_ratio}")

    worst_corner = min(corners.top_left, corners.top_right,
                       corners.bottom_left, corners.bottom_right)
    if   worst_corner < 18: notes.append("Heavy corner wear detected")
    elif worst_corner < 40: notes.append("Light corner wear")
    else:                   notes.append("Corners appear sharp")

    notes.extend(surface.flags)

    return notes


# ---------------------------------------------------------------------------
# Debug image generation
# ---------------------------------------------------------------------------

def _encode_png(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode('.png', img)
    if not ok:
        raise RuntimeError("PNG encoding failed")
    return buf.tobytes()


def _put_label(img: np.ndarray, text: str, x: int, y: int,
               color=(220, 220, 220), scale: float = 0.50, thick: int = 2) -> None:
    """Outlined text readable against any background colour."""
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(img, text, (x, y), font, scale, (0, 0, 0), thick + 2, cv2.LINE_AA)
    cv2.putText(img, text, (x, y), font, scale, color,     thick,     cv2.LINE_AA)


def _score_color(score: int) -> tuple[int, int, int]:
    if score >= 9: return (0, 200,  80)
    if score >= 7: return (0, 210, 170)
    if score >= 5: return (0, 150, 255)
    return (0, 60, 255)


def _add_step_header(
    canvas: np.ndarray,
    step: int,
    title: str,
    score: Optional[int] = None,
    extra: str = "",
) -> np.ndarray:
    """Prepend a 28-px dark header bar showing step number, title, optional score."""
    BAR_H = 28
    w = canvas.shape[1]
    bar = np.full((BAR_H, w, 3), 18, dtype=np.uint8)
    label = f"Step {step}  ·  {title}"
    if extra:
        label += f"  ·  {extra}"
    _put_label(bar, label, 8, 20, (200, 200, 200), scale=0.46)
    if score is not None:
        sc = _score_color(score)
        _put_label(bar, f"{score}/10", w - 52, 20, sc, scale=0.52)
    return np.vstack([bar, canvas])


def _debug_boundary(
    img: np.ndarray,
    outer_xywh: Optional[tuple[int, int, int, int]] = None,
    inner_xywh: Optional[tuple[int, int, int, int]] = None,
    src_quad: Optional[np.ndarray] = None,
    strategy_name: str = "",
    confidence_pts: int = 0,
) -> bytes:
    """
    Step 1 — shows the original image with the detected or user-guided card
    boundary drawn on it, labeled with strategy name and confidence level.
    """
    DISP_W = 600
    ih, iw = img.shape[:2]
    scale  = min(1.0, DISP_W / iw)
    dw     = int(iw * scale)
    dh     = int(ih * scale)
    vis    = cv2.resize(img, (dw, dh))

    GREEN  = (80,  210, 80)
    ORANGE = (80,  150, 255)

    if outer_xywh:
        ox, oy, ow, oh = outer_xywh
        s = scale
        pts = np.array([
            [ox*s,      oy*s      ],
            [(ox+ow)*s, oy*s      ],
            [(ox+ow)*s, (oy+oh)*s ],
            [ox*s,      (oy+oh)*s ],
        ], dtype=np.int32)
        cv2.polylines(vis, [pts.reshape(1, -1, 2)], True, GREEN, 2, cv2.LINE_AA)
        for pt in pts:
            cv2.circle(vis, tuple(pt), 5, GREEN, -1, cv2.LINE_AA)
        if inner_xywh:
            ix, iy, iw2, ih2 = inner_xywh
            ipts = np.array([
                [ix*s,       iy*s       ],
                [(ix+iw2)*s, iy*s       ],
                [(ix+iw2)*s, (iy+ih2)*s ],
                [ix*s,       (iy+ih2)*s ],
            ], dtype=np.int32)
            cv2.polylines(vis, [ipts.reshape(1, -1, 2)], True, ORANGE, 2, cv2.LINE_AA)
        mode_text = "Guide-assisted  ·  outer=green  inner=orange"
        conf_pts  = 4
    elif src_quad is not None:
        pts = (src_quad * scale).astype(np.int32)
        cv2.polylines(vis, [pts.reshape(1, -1, 2)], True, GREEN, 2, cv2.LINE_AA)
        for pt in pts:
            cv2.circle(vis, tuple(pt), 5, (0, 255, 100), -1, cv2.LINE_AA)
        mode_text = f"Auto  ·  {strategy_name}"
        conf_pts  = confidence_pts
    else:
        _put_label(vis, "No boundary detected — full image resized", 10, 28, (80, 80, 255), scale=0.5)
        mode_text = strategy_name or "Resize fallback"
        conf_pts  = 0

    conf_str   = "HIGH" if conf_pts == 4 else ("MEDIUM" if conf_pts == 2 else "LOW")
    conf_color = (0, 200, 80) if conf_pts == 4 else ((0, 200, 200) if conf_pts == 2 else (0, 60, 255))

    BAR_H  = 28
    canvas = np.full((dh + BAR_H, dw, 3), 18, dtype=np.uint8)
    canvas[BAR_H:] = vis
    _put_label(canvas, f"Step 1  ·  Boundary  ·  {mode_text}", 8, 20, (200, 200, 200), scale=0.46)
    _put_label(canvas, conf_str, dw - 68, 20, conf_color, scale=0.48)
    return _encode_png(canvas)


def _debug_rectified(
    rectified: np.ndarray,
    strategy_name: str = "",
    confidence_pts: int = 4,
) -> bytes:
    """Step 2 — perspective-corrected card with strategy name and confidence."""
    conf_str   = "HIGH" if confidence_pts == 4 else ("MEDIUM" if confidence_pts == 2 else "LOW")
    conf_color = (0, 200, 80) if confidence_pts == 4 else ((0, 200, 200) if confidence_pts == 2 else (0, 60, 255))
    extra      = strategy_name if strategy_name else ""
    canvas     = _add_step_header(rectified, 2, "Rectification", extra=extra)
    # Overwrite the auto-generated score slot with the confidence badge
    w = canvas.shape[1]
    _put_label(canvas, conf_str, w - 68, 20, conf_color, scale=0.48)
    return _encode_png(canvas)


def _debug_centering(
    rect: np.ndarray,
    hint_left: Optional[float] = None,
    hint_right: Optional[float] = None,
    hint_top: Optional[float] = None,
    hint_bottom: Optional[float] = None,
) -> bytes:
    h, w = rect.shape[:2]
    vis  = rect.copy()
    gray = cv2.cvtColor(rect, cv2.COLOR_BGR2GRAY)

    band = 12
    mid_y, mid_x = h // 2, w // 2

    overlay = vis.copy()
    cv2.rectangle(overlay, (0, mid_y - band), (w - 1, mid_y + band), (20, 20, 20), -1)
    cv2.rectangle(overlay, (mid_x - band, 0), (mid_x + band, h - 1), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.25, vis, 0.75, 0, vis)

    h_row = gray[mid_y - band : mid_y + band, :].mean(axis=0)
    v_col = gray[:, mid_x - band : mid_x + band].mean(axis=1)

    GRAY = (150, 150, 150)

    if hint_left is not None:
        left_px   = _guided_find_border(h_row,       hint_left)
        right_px  = _guided_find_border(h_row[::-1], hint_right)
        top_px    = _guided_find_border(v_col,       hint_top)
        bottom_px = _guided_find_border(v_col[::-1], hint_bottom)
        # Draw ±window boxes around each hint so the user can see the search zone
        for hint, is_end, axis in [
            (hint_left, False, "h"), (hint_right, True, "h"),
            (hint_top,  False, "v"), (hint_bottom, True, "v"),
        ]:
            win = max(int(max(hint, 1.0) * 0.15), 8)
            hi  = int(round(hint))
            lo_px, hi_px = max(0, hi - win), min((w if axis == "h" else h) - 1, hi + win)
            if axis == "h":
                x = (w - 1 - hi_px) if is_end else lo_px
                xe = (w - 1 - lo_px) if is_end else hi_px
                cv2.rectangle(vis, (x, 0), (xe, h - 1), GRAY, 1)
            else:
                y = (h - 1 - hi_px) if is_end else lo_px
                ye = (h - 1 - lo_px) if is_end else hi_px
                cv2.rectangle(vis, (0, y), (w - 1, ye), GRAY, 1)
    else:
        sw = max(int(w * _BORDER_SEARCH), 40)
        sh = max(int(h * _BORDER_SEARCH), 56)
        left_px   = _find_inner_border(h_row, sw)
        right_px  = _find_inner_border(h_row, sw, from_end=True)
        top_px    = _find_inner_border(v_col, sh)
        bottom_px = _find_inner_border(v_col, sh, from_end=True)
        cv2.rectangle(vis, (0, 0),     (sw, h - 1),    GRAY, 1)
        cv2.rectangle(vis, (w-sw-1,0), (w - 1, h - 1), GRAY, 1)
        cv2.rectangle(vis, (0, 0),     (w - 1, sh),     GRAY, 1)
        cv2.rectangle(vis, (0, h-sh),  (w - 1, h - 1), GRAY, 1)

    right_x  = w - 1 - int(right_px)
    bottom_y = h - 1 - int(bottom_px)

    total_h = left_px + right_px
    total_v = top_px + bottom_px
    lp = round(left_px  / total_h * 100, 1) if total_h >= 4 else 50.0
    rp = round(100 - lp, 1)                 if total_h >= 4 else 50.0
    tp = round(top_px   / total_v * 100, 1) if total_v >= 4 else 50.0
    bp = round(100 - tp, 1)                 if total_v >= 4 else 50.0

    GREEN   = (0, 210, 0)
    RED     = (0, 60, 255)
    YELLOW  = (0, 210, 210)
    MAGENTA = (210, 0, 210)

    cv2.line(vis, (int(left_px), 0),  (int(left_px), h - 1),  GREEN,   2, cv2.LINE_AA)
    cv2.line(vis, (right_x, 0),       (right_x, h - 1),        RED,     2, cv2.LINE_AA)
    cv2.line(vis, (0, int(top_px)),   (w - 1, int(top_px)),    YELLOW,  2, cv2.LINE_AA)
    cv2.line(vis, (0, bottom_y),      (w - 1, bottom_y),       MAGENTA, 2, cv2.LINE_AA)

    _put_label(vis, f"L: {lp}%",  int(left_px) + 6,        mid_y - 10,   GREEN)
    _put_label(vis, f"R: {rp}%",  max(right_x - 75, 5),    mid_y - 10,   RED)
    _put_label(vis, f"T: {tp}%",  mid_x + 6,               int(top_px) + 20, YELLOW)
    _put_label(vis, f"B: {bp}%",  mid_x + 6,               bottom_y - 6, MAGENTA)

    # --- Ratio bars footer ---
    score = _centering_score_from_pcts(lp, rp, tp, bp)

    FOOT_H = 52
    footer = np.full((FOOT_H, w, 3), 28, dtype=np.uint8)
    BAR_W  = w - 120
    BAR_H2 = 10

    def _ratio_bar(canvas: np.ndarray, y: int, pct_a: float, color_a: tuple, color_b: tuple,
                   label_a: str, label_b: str) -> None:
        split = int(BAR_W * pct_a / 100)
        x0 = 60
        cv2.rectangle(canvas, (x0, y),          (x0 + split, y + BAR_H2),        color_a, -1)
        cv2.rectangle(canvas, (x0 + split, y),  (x0 + BAR_W, y + BAR_H2),        color_b, -1)
        cv2.rectangle(canvas, (x0, y),          (x0 + BAR_W, y + BAR_H2),        (80, 80, 80), 1)
        _put_label(canvas, label_a, 4,          y + BAR_H2 - 1, color_a,  scale=0.36)
        _put_label(canvas, label_b, x0 + BAR_W + 4, y + BAR_H2 - 1, color_b, scale=0.36)

    _ratio_bar(footer,  8, lp, GREEN,   RED,     f"L {lp}%",  f"R {rp}%")
    _ratio_bar(footer, 32, tp, YELLOW, MAGENTA,  f"T {tp}%",  f"B {bp}%")

    canvas = np.vstack([vis, footer])
    canvas = _add_step_header(canvas, 3, "Centering", score=score,
                              extra=f"L/R {round(lp)}/{round(rp)}  T/B {round(tp)}/{round(bp)}")
    return _encode_png(canvas)


def _debug_corners(rect: np.ndarray) -> bytes:
    h, w = rect.shape[:2]
    cw = max(int(w * 0.10), 35)
    ch = max(int(h * 0.10), 48)

    corners_info = [
        ("TL", rect[:ch,     :cw   ]),
        ("TR", rect[:ch,     w-cw: ]),
        ("BL", rect[h-ch:,   :cw   ]),
        ("BR", rect[h-ch:,   w-cw: ]),
    ]

    UP    = 2
    PAD   = 8
    LBL_H = 22

    # Each cell: [original 2x | sobel heatmap 2x] side by side
    cell_w = cw * UP * 2 + PAD
    cell_h = ch * UP + LBL_H + PAD

    canvas_h = cell_h * 2 + PAD * 3
    canvas_w = cell_w * 2 + PAD * 3
    canvas   = np.full((canvas_h, canvas_w, 3), 28, dtype=np.uint8)

    for idx, (name, patch) in enumerate(corners_info):
        row, col = divmod(idx, 2)
        x0 = PAD + col * (cell_w + PAD)
        y0 = PAD + row * (cell_h + PAD)

        gray_p  = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
        up_orig = cv2.resize(patch,  (cw * UP, ch * UP), interpolation=cv2.INTER_CUBIC)
        up_gray = cv2.resize(gray_p, (cw * UP, ch * UP), interpolation=cv2.INTER_CUBIC)

        sx   = cv2.Sobel(up_gray.astype(np.float32), cv2.CV_32F, 1, 0, ksize=3)
        sy   = cv2.Sobel(up_gray.astype(np.float32), cv2.CV_32F, 0, 1, ksize=3)
        grad = np.sqrt(sx ** 2 + sy ** 2)

        grad_norm  = (grad / (grad.max() + 1e-5) * 255).astype(np.uint8)
        grad_color = cv2.applyColorMap(grad_norm, cv2.COLORMAP_INFERNO)

        cell_img = np.hstack([up_orig, grad_color])

        yp = y0 + LBL_H
        canvas[yp : yp + ch * UP, x0 : x0 + cw * UP * 2] = cell_img

        score = _corner_sharpness(patch)
        col_c = (0, 200, 0) if score >= 60 else ((0, 180, 200) if score >= 35 else (0, 60, 220))
        _put_label(canvas, f"{name}: {score:.0f}/100  (left=original, right=sobel)", x0, y0 + LBL_H - 5, col_c)

    # Mini card overview — scaled-down full card with corner patch boxes highlighted
    THUMB_W, THUMB_H = 80, 112
    thumb = cv2.resize(rect, (THUMB_W, THUMB_H))
    pw = max(int(THUMB_W * 0.10), 8)
    ph = max(int(THUMB_H * 0.10), 10)
    highlights = [
        ((0, 0), (pw, ph)),
        ((THUMB_W - pw, 0), (THUMB_W, ph)),
        ((0, THUMB_H - ph), (pw, THUMB_H)),
        ((THUMB_W - pw, THUMB_H - ph), (THUMB_W, THUMB_H)),
    ]
    ovl = thumb.copy()
    for (x1, y1), (x2, y2) in highlights:
        cv2.rectangle(ovl, (x1, y1), (x2 - 1, y2 - 1), (0, 220, 100), 1)
    cv2.addWeighted(ovl, 0.7, thumb, 0.3, 0, thumb)
    for (x1, y1), (x2, y2) in highlights:
        cv2.rectangle(thumb, (x1, y1), (x2 - 1, y2 - 1), (0, 220, 100), 1)

    THUMB_PAD = 8
    t_x = canvas_w - THUMB_W - THUMB_PAD
    t_y = THUMB_PAD
    canvas[t_y : t_y + THUMB_H, t_x : t_x + THUMB_W] = thumb
    _put_label(canvas, "Patch locations", t_x, t_y + THUMB_H + 12, (140, 140, 140), scale=0.30)

    vals = sorted([_corner_sharpness(rect[:ch, :cw]), _corner_sharpness(rect[:ch, w-cw:]),
                   _corner_sharpness(rect[h-ch:, :cw]), _corner_sharpness(rect[h-ch:, w-cw:])])
    worst_avg = (vals[0] + vals[1]) / 2
    if   worst_avg >= 75: overall = 10
    elif worst_avg >= 60: overall = 9
    elif worst_avg >= 45: overall = 8
    elif worst_avg >= 32: overall = 7
    elif worst_avg >= 22: overall = 6
    elif worst_avg >= 14: overall = 5
    elif worst_avg >=  8: overall = 4
    else:                 overall = max(1, round(worst_avg / 3))

    canvas = _add_step_header(canvas, 4, "Corners", score=overall,
                              extra=f"worst pair avg {worst_avg:.0f}/100")
    return _encode_png(canvas)


def _debug_surface(rect: np.ndarray) -> bytes:
    h, w = rect.shape[:2]
    mx = int(w * 0.15)
    my = int(h * 0.15)
    artwork = rect[my : h - my, mx : w - mx]
    gray    = cv2.cvtColor(artwork, cv2.COLOR_BGR2GRAY)

    k_h  = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 1))
    k_v  = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 25))
    th_h = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, k_h)
    th_v = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, k_v)

    th_h_mean = float(th_h.mean())
    th_v_mean = float(th_v.mean())
    max_d = max(th_h_mean, th_v_mean, 0.001)
    min_d = min(th_h_mean, th_v_mean)
    sym   = min_d / max_d
    risk  = round(float(min((max_d / 30.0) * (1.0 - sym * 0.85), 1.0)), 3)

    DISP_W = 250
    scale  = DISP_W / artwork.shape[1]
    disp_h = int(artwork.shape[0] * scale)

    orig_disp = cv2.resize(artwork, (DISP_W, disp_h))

    th_h_enh = np.clip(th_h.astype(np.uint16) * 5, 0, 255).astype(np.uint8)
    th_v_enh = np.clip(th_v.astype(np.uint16) * 5, 0, 255).astype(np.uint8)
    th_h_disp = cv2.resize(cv2.applyColorMap(th_h_enh, cv2.COLORMAP_HOT),  (DISP_W, disp_h))
    th_v_disp = cv2.resize(cv2.applyColorMap(th_v_enh, cv2.COLORMAP_COOL), (DISP_W, disp_h))

    PAD   = 8
    LBL_H = 30

    canvas_w = DISP_W * 3 + PAD * 4
    canvas_h = disp_h + LBL_H + PAD * 2
    canvas   = np.full((canvas_h, canvas_w, 3), 28, dtype=np.uint8)

    holo_label = "holo pattern" if sym > 0.7 else ("mixed" if sym > 0.4 else "directional")
    if   risk < 0.15: score = 10
    elif risk < 0.25: score = 9
    elif risk < 0.38: score = 8
    elif risk < 0.50: score = 7
    elif risk < 0.65: score = 6
    elif risk < 0.80: score = 5
    elif risk < 0.92: score = 4
    else:             score = 3

    panels = [
        (orig_disp,  "Original (inner 70%)",                              (200, 200, 200)),
        (th_h_disp,  f"Top-hat H  mean={th_h_mean:.2f}  (horizontal lines)", (80, 160, 255)),
        (th_v_disp,  f"Top-hat V  mean={th_v_mean:.2f}  (vertical lines)",   (255, 140, 60)),
    ]

    for i, (panel, title, color) in enumerate(panels):
        x0 = PAD + i * (DISP_W + PAD)
        y0 = PAD + LBL_H
        canvas[y0 : y0 + disp_h, x0 : x0 + DISP_W] = panel
        _put_label(canvas, title, x0, y0 - 8, color, scale=0.42)

    holo_disc = f"holo discount {round(sym * 85)}%" if sym > 0.35 else "no holo discount"
    canvas = _add_step_header(
        canvas, 5, "Surface", score=score,
        extra=f"risk={risk:.2f}  sym={sym:.2f} ({holo_label})  {holo_disc}",
    )
    return _encode_png(canvas)


def _debug_edges(rect: np.ndarray) -> bytes:
    """
    Four-panel edge diagnostic.  For each edge (Top / Bottom / Left / Right):
      • Zoomed pixel strip  — the actual 6-px measurement band, scaled to be visible
      • Deviation heatmap   — per-column deviation from the strip mean:
                              green = uniform/clean, red = varying/chipped
      • Intensity profile   — per-column mean intensity as a line chart; spikes
                              reveal isolated chips, elevated baseline = general wear
    """
    h, w  = rect.shape[:2]
    gray  = cv2.cvtColor(rect, cv2.COLOR_BGR2GRAY)
    skip  = 3
    strip = 6
    PW    = w   # panel width — keep same as card width (630)

    # Each entry: (label, color strip (6,L,3), gray strip (6,L))
    # Left/Right strips are transposed so the long axis runs horizontally.
    edge_strips = [
        ("Top",
         rect[skip:skip+strip,        skip:w-skip],
         gray[skip:skip+strip,        skip:w-skip]),
        ("Bottom",
         rect[h-skip-strip:h-skip,    skip:w-skip],
         gray[h-skip-strip:h-skip,    skip:w-skip]),
        ("Left",
         rect[skip:h-skip, skip:skip+strip        ].transpose(1, 0, 2),
         gray[skip:h-skip, skip:skip+strip        ].T),
        ("Right",
         rect[skip:h-skip, w-skip-strip:w-skip    ].transpose(1, 0, 2),
         gray[skip:h-skip, w-skip-strip:w-skip    ].T),
    ]

    PIXEL_H  = 28   # zoomed strip height
    HEAT_H   = 14   # deviation heatmap height
    GRAPH_H  = 50   # intensity profile height
    LBL_H    = 22
    INNER_PAD = 3
    PANEL_H  = LBL_H + INNER_PAD + PIXEL_H + INNER_PAD + HEAT_H + INNER_PAD + GRAPH_H
    OUTER_PAD = 5

    canvas_h = OUTER_PAD + (PANEL_H + OUTER_PAD) * 4
    canvas   = np.full((canvas_h, PW, 3), 18, dtype=np.uint8)

    stds: list[tuple[str, float]] = []

    for i, (name, strip_bgr, strip_g) in enumerate(edge_strips):
        std_val   = float(strip_g.std())
        col_mean  = strip_g.mean(axis=0).astype(np.float32)   # (L,)
        col_std   = strip_g.std(axis=0).astype(np.float32)    # (L,) — per-position variation
        stds.append((name, std_val))

        y0 = OUTER_PAD + i * (PANEL_H + OUTER_PAD)

        # ── Label ──────────────────────────────────────────────────────────
        sc = (0,200,80) if std_val < 10 else ((0,210,170) if std_val < 28 else
              ((0,150,255) if std_val < 55 else (0,60,255)))
        _put_label(canvas, f"{name}  σ = {std_val:.1f}", 8, y0 + LBL_H - 3, sc, scale=0.46)

        # Grade thresholds for quick reference alongside the σ value
        thresholds = [(10,"10"),(18,"9"),(28,"8"),(40,"7"),(55,"6"),(70,"5"),(90,"4"),(110,"3")]
        grade_str = next((g for t, g in thresholds if std_val < t), "2")
        _put_label(canvas, f"→ grade {grade_str}", PW - 95, y0 + LBL_H - 3,
                   (140, 140, 140), scale=0.40)

        # ── Zoomed pixel strip ─────────────────────────────────────────────
        # Scale strip to full panel width; use INTER_NEAREST to show real pixels
        y_pix = y0 + LBL_H + INNER_PAD
        disp_pix = cv2.resize(strip_bgr, (PW, PIXEL_H), interpolation=cv2.INTER_NEAREST)
        canvas[y_pix : y_pix + PIXEL_H] = disp_pix

        # ── Deviation heatmap ──────────────────────────────────────────────
        # Per-column deviation from strip mean → 0-255 → colormap
        # 0 = perfectly uniform (green), 255 = maximum variation (red)
        y_heat = y_pix + PIXEL_H + INNER_PAD
        max_dev = max(col_std.max(), 1.0)
        dev_norm = np.clip(col_std / max_dev * 255, 0, 255).astype(np.uint8)
        # TURBO: 0→blue(clean), 255→red(worn) — intuitive hot/cold mapping
        heat_row = cv2.applyColorMap(dev_norm[None, :], cv2.COLORMAP_TURBO)  # (1,L,3)
        heat_disp = cv2.resize(heat_row, (PW, HEAT_H), interpolation=cv2.INTER_LINEAR)
        canvas[y_heat : y_heat + HEAT_H] = heat_disp

        # ── Intensity profile graph ────────────────────────────────────────
        y_graph = y_heat + HEAT_H + INNER_PAD
        graph   = np.full((GRAPH_H, PW, 3), 28, dtype=np.uint8)

        # Resample mean signal and ±1σ band to PW points
        L = len(col_mean)
        xs = np.linspace(0, L - 1, PW).astype(int)
        sig   = col_mean[xs]
        band  = col_std[xs]

        sig_min = max(sig.min() - 5, 0)
        sig_max = min(sig.max() + 5, 255)
        rng = max(sig_max - sig_min, 1.0)

        def _to_y(v: np.ndarray) -> np.ndarray:
            return np.clip(
                ((1.0 - (v - sig_min) / rng) * (GRAPH_H - 6) + 3).astype(int),
                0, GRAPH_H - 1,
            )

        # ±1σ shaded band
        y_hi = _to_y(sig + band)
        y_lo = _to_y(sig - band)
        for x in range(PW):
            top_y = min(y_hi[x], y_lo[x])
            bot_y = max(y_hi[x], y_lo[x])
            cv2.line(graph, (x, top_y), (x, bot_y), (50, 70, 50), 1)

        # Mean intensity line
        ys = _to_y(sig)
        for x in range(PW - 1):
            cv2.line(graph, (x, ys[x]), (x + 1, ys[x + 1]), (120, 200, 120), 1, cv2.LINE_AA)

        # Horizontal reference: overall strip mean
        mean_y = int(_to_y(np.array([strip_g.mean()]))[0])
        cv2.line(graph, (0, mean_y), (PW - 1, mean_y), (60, 60, 60), 1)
        _put_label(graph, "mean", 2, max(mean_y - 2, 10), (80, 80, 80), scale=0.30)

        canvas[y_graph : y_graph + GRAPH_H] = graph

        # Divider between panels
        if i < 3:
            div_y = y0 + PANEL_H + OUTER_PAD // 2
            cv2.line(canvas, (0, div_y), (PW - 1, div_y), (38, 38, 38), 1)

    worst_name, worst_val = max(stds, key=lambda x: x[1])
    worst = worst_val
    if   worst < 10: score = 10
    elif worst < 18: score = 9
    elif worst < 28: score = 8
    elif worst < 40: score = 7
    elif worst < 55: score = 6
    elif worst < 70: score = 5
    elif worst < 90: score = 4
    elif worst < 110: score = 3
    else:             score = 2

    canvas = _add_step_header(canvas, 6, "Edges  (informational — not included in grade)",
                              score=score,
                              extra=f"worst: {worst_name} σ={worst_val:.1f}  ·  "
                                    f"pixel strip / deviation heatmap / intensity profile")
    return _encode_png(canvas)


def _debug_grade(report: GradeReport) -> bytes:
    """
    Step 7 — scorecard showing all 4 dimension scores, their weights, the
    weighted formula, and the final grade.
    """
    W, H = 630, 260
    canvas = np.full((H, W, 3), 22, dtype=np.uint8)

    dims = [
        ("Centering", report.centering.score, 40),
        ("Corners",   report.corners.score,   40),
        ("Surface",   report.surface.score,   20),
    ]

    BAR_X  = 140
    BAR_LEN = 280
    ROW_H  = 48

    for i, (name, score, weight) in enumerate(dims):
        y = 32 + i * ROW_H
        bar_fill = int(BAR_LEN * score / 10)
        sc = _score_color(score)
        cv2.rectangle(canvas, (BAR_X, y - 10), (BAR_X + BAR_LEN, y + 6), (45, 45, 45), -1)
        cv2.rectangle(canvas, (BAR_X, y - 10), (BAR_X + bar_fill, y + 6), sc, -1)
        _put_label(canvas, f"{name} × {weight}%", 8, y, (180, 180, 180), scale=0.44)
        _put_label(canvas, f"{score}/10", BAR_X + BAR_LEN + 8, y, sc, scale=0.50)

    # Edges shown but excluded
    e_score = report.edges.score
    ey      = 32 + 3 * ROW_H
    cv2.rectangle(canvas, (BAR_X, ey - 10), (BAR_X + BAR_LEN, ey + 6), (35, 35, 35), -1)
    _put_label(canvas, "Edges  (excluded)", 8, ey, (70, 70, 70), scale=0.44)
    _put_label(canvas, f"{e_score}/10", BAR_X + BAR_LEN + 8, ey, (70, 70, 70), scale=0.50)

    # Formula row
    c, k, s = [d[1] for d in dims]
    raw   = c * 0.40 + k * 0.40 + s * 0.20
    grade = max(1.0, min(10.0, round(raw * 2) / 2))
    formula = f"{c}×0.40 + {k}×0.40 + {s}×0.20  =  {raw:.2f}  →  {grade:.1f}"
    _put_label(canvas, formula, 8, H - 52, (120, 120, 120), scale=0.40)

    # Final grade — large
    grade_color = _score_color(int(round(grade)))
    cv2.putText(canvas, f"{grade:.1f}", (BAR_X + BAR_LEN + 60, H - 30),
                cv2.FONT_HERSHEY_SIMPLEX, 1.8, (0, 0, 0), 6, cv2.LINE_AA)
    cv2.putText(canvas, f"{grade:.1f}", (BAR_X + BAR_LEN + 60, H - 30),
                cv2.FONT_HERSHEY_SIMPLEX, 1.8, grade_color, 3, cv2.LINE_AA)
    _put_label(canvas, report.grade_label, BAR_X + BAR_LEN + 56, H - 12,
               grade_color, scale=0.44)

    canvas = _add_step_header(canvas, 7, "Grade Summary",
                              extra=f"{report.grade_label}  ·  confidence {report.confidence.upper()}")
    return _encode_png(canvas)


def generate_debug_images(
    image_bytes: bytes,
    outer_xywh: Optional[tuple[int, int, int, int]] = None,
    inner_xywh: Optional[tuple[int, int, int, int]] = None,
) -> dict[str, bytes]:
    """
    Return diagnostic PNGs for each grading dimension.

    When outer_xywh is provided the perspective warp uses the guide rectangle
    instead of auto-detection, matching what analyze_card_guided actually did.
    When inner_xywh is also provided the centering view uses guide-seeded
    gradient detection rather than the fixed 22% search zone.

    Keys (in pipeline order):
      "boundary", "rectified", "centering", "corners", "surface", "edges", "grade"
    """
    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image")

    hint_left = hint_right = hint_top = hint_bottom = None
    strategy_name  = ""
    confidence_pts = 4
    src_quad: Optional[np.ndarray] = None

    if outer_xywh:
        ox, oy, ow, oh = outer_xywh
        src = np.float32([[ox, oy], [ox + ow, oy], [ox + ow, oy + oh], [ox, oy + oh]])
        dst = np.float32([[0, 0], [_W - 1, 0], [_W - 1, _H - 1], [0, _H - 1]])
        M   = cv2.getPerspectiveTransform(src, dst)
        rectified      = cv2.warpPerspective(img, M, (_W, _H))
        strategy_name  = "Guide-assisted"
        confidence_pts = 4

        if inner_xywh:
            ix, iy, iw, ih = inner_xywh
            inner_corners = np.float32([
                [ix,      iy],
                [ix + iw, iy],
                [ix + iw, iy + ih],
                [ix,      iy + ih],
            ]).reshape(1, -1, 2)
            wp = cv2.perspectiveTransform(inner_corners, M).reshape(-1, 2)
            hint_left   = max(0.0, float(wp[:, 0].min()))
            hint_right  = max(0.0, float(_W - wp[:, 0].max()))
            hint_top    = max(0.0, float(wp[:, 1].min()))
            hint_bottom = max(0.0, float(_H - wp[:, 1].max()))
    else:
        rectified, confidence_pts, strategy_name, src_quad = _rectify(img)

    report = analyze_card_guided(image_bytes, outer_xywh, inner_xywh)

    return {
        "boundary":  _debug_boundary(img, outer_xywh, inner_xywh, src_quad,
                                     strategy_name, confidence_pts),
        "rectified": _debug_rectified(rectified, strategy_name, confidence_pts),
        "centering": _debug_centering(rectified, hint_left, hint_right, hint_top, hint_bottom),
        "corners":   _debug_corners(rectified),
        "surface":   _debug_surface(rectified),
        "edges":     _debug_edges(rectified),
        "grade":     _debug_grade(report),
    }
