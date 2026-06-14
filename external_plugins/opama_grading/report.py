"""
Grading report image generator.

Produces a landscape PNG combining the card scan thumbnail with a clean
breakdown of the grade estimate — suitable for listings and record-keeping.

Fonts: uses DejaVu Sans (present in the Docker image via tesseract-ocr
dependencies).  Falls back to PIL's built-in bitmap font if unavailable.
"""

from __future__ import annotations

import io
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Colour palette  (matches the frontend dark/slate theme)
# ---------------------------------------------------------------------------
_WHITE   = (255, 255, 255)
_BG      = (248, 250, 252)      # slate-50
_HEADER  = (15,  23,  42)       # slate-900
_DARK    = (30,  41,  59)       # slate-800
_MED     = (71,  85, 105)       # slate-600
_LIGHT   = (148, 163, 184)      # slate-400
_RULE    = (226, 232, 240)      # slate-200
_PANEL   = (241, 245, 249)      # slate-100

_EMERALD = (16,  185, 129)
_LIME    = (132, 204,  22)
_AMBER   = (245, 158,  11)
_RED     = (239,  68,  68)


# ---------------------------------------------------------------------------
# Font helpers
# ---------------------------------------------------------------------------

_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]
_FONT_REGULAR = [p.replace("-Bold", "") for p in _FONT_PATHS] + _FONT_PATHS


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    paths = _FONT_PATHS if bold else _FONT_REGULAR
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def _text_w(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0]


# ---------------------------------------------------------------------------
# Score colour helpers
# ---------------------------------------------------------------------------

def _score_color(score: int) -> tuple:
    if score >= 9: return _EMERALD
    if score >= 7: return _LIME
    if score >= 5: return _AMBER
    return _RED


def _grade_color(grade: float) -> tuple:
    if grade >= 9: return _EMERALD
    if grade >= 7: return _LIME
    if grade >= 5: return _AMBER
    return _RED


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_report(
    *,
    grade: float,
    grade_label: str,
    card_name: Optional[str],
    card_number: Optional[str],
    centering_score: int,
    lr_ratio: str,
    tb_ratio: str,
    corner_score: int,
    corner_tl: float,
    corner_tr: float,
    corner_bl: float,
    corner_br: float,
    surface_score: int,
    scratch_risk: float,
    edge_score: int,
    notes: list[str],
    confidence: str,
    analyzed_at: str,
    scan_bytes: Optional[bytes] = None,
) -> bytes:
    """Return the report as PNG bytes."""

    W, H = 860, 520
    img = Image.new("RGB", (W, H), _BG)
    d   = ImageDraw.Draw(img)

    f_hdr    = _font(20, bold=True)
    f_grade  = _font(72, bold=True)
    f_lbl    = _font(17, bold=True)
    f_sub    = _font(13)
    f_bar    = _font(13, bold=True)
    f_note   = _font(12)
    f_tiny   = _font(11)

    # ── Header ──────────────────────────────────────────────────────────────
    d.rectangle([0, 0, W, 52], fill=_HEADER)
    d.text((20, 14), "CARD GRADER  REPORT", font=f_hdr, fill=_WHITE)

    # Confidence badge (top-right)
    conf_color = _EMERALD if confidence == "high" else (_AMBER if confidence == "medium" else _LIGHT)
    badge = f"{confidence.upper()} CONFIDENCE"
    bw = _text_w(d, badge, f_tiny) + 16
    d.rounded_rectangle([W - bw - 12, 14, W - 12, 38], radius=4, fill=conf_color)
    d.text((W - bw - 4, 18), badge, font=f_tiny, fill=_WHITE)

    # Date
    date_str = analyzed_at[:10] if analyzed_at else ""
    d.text((W - _text_w(d, date_str, f_tiny) - 12, 42), date_str, font=f_tiny, fill=_LIGHT)

    # ── Card thumbnail ───────────────────────────────────────────────────────
    THUMB_X, THUMB_Y = 16, 64
    THUMB_W, THUMB_H = 190, 266

    d.rectangle([THUMB_X, THUMB_Y, THUMB_X + THUMB_W, THUMB_Y + THUMB_H],
                fill=_PANEL, outline=_RULE)

    if scan_bytes:
        try:
            scan = Image.open(io.BytesIO(scan_bytes)).convert("RGB")
            scan.thumbnail((THUMB_W - 4, THUMB_H - 4), Image.LANCZOS)
            px = THUMB_X + (THUMB_W - scan.width) // 2
            py = THUMB_Y + (THUMB_H - scan.height) // 2
            img.paste(scan, (px, py))
        except Exception:
            d.text((THUMB_X + 50, THUMB_Y + THUMB_H // 2 - 8),
                   "No scan", font=f_tiny, fill=_LIGHT)

    # Card name/number beneath thumbnail
    if card_name:
        name_display = card_name[:22] + "…" if len(card_name) > 22 else card_name
        d.text((THUMB_X, THUMB_Y + THUMB_H + 8), name_display, font=f_sub, fill=_DARK)
    if card_number:
        d.text((THUMB_X, THUMB_Y + THUMB_H + 26), f"#{card_number}", font=f_tiny, fill=_MED)

    # ── Grade ────────────────────────────────────────────────────────────────
    GX = 228   # left edge of grade + scores panel

    grade_str = f"{grade:.1f}"
    d.text((GX, 58), grade_str, font=f_grade, fill=_grade_color(grade))
    gw = _text_w(d, grade_str, f_grade)
    d.text((GX + gw + 10, 90), grade_label, font=f_lbl, fill=_MED)

    d.line([GX, 148, W - 16, 148], fill=_RULE, width=1)

    # ── Score bars ──────────────────────────────────────────────────────────
    BAR_LEFT  = GX + 100
    BAR_W     = W - BAR_LEFT - 70
    BAR_H     = 13
    ROW       = 38
    START_Y   = 160
    DOT_R     = 6
    DOT_G     = 14  # centre-to-centre gap

    def _cdot(cx: int, cy: int, val: float) -> None:
        c = _EMERALD if val >= 70 else (_AMBER if val >= 45 else _RED)
        d.ellipse([cx - DOT_R, cy - DOT_R, cx + DOT_R, cy + DOT_R], fill=c)

    dims = [
        ("Centering", centering_score, f"L/R {lr_ratio}  ·  T/B {tb_ratio}"),
        ("Corners",   corner_score,    None),
        ("Surface",   surface_score,   f"scratch risk {scratch_risk * 100:.0f}%"),
        ("Edges",     edge_score,      None),
    ]

    for i, (lbl, sc, sub) in enumerate(dims):
        by = START_Y + i * ROW
        d.text((GX, by), lbl, font=f_bar, fill=_MED)
        if sub:
            d.text((GX, by + 15), sub, font=f_tiny, fill=_LIGHT)
        elif lbl == "Corners":
            # 2×2 dot diagram in the sub-label slot (TL/TR/BL/BR corner quality).
            # Placed here so it doesn't collide with the score text on the right.
            dx, dy = GX + 2, by + 17
            _cdot(dx,          dy,          corner_tl)
            _cdot(dx + DOT_G,  dy,          corner_tr)
            _cdot(dx,          dy + DOT_G,  corner_bl)
            _cdot(dx + DOT_G,  dy + DOT_G,  corner_br)
        # Bar background
        d.rounded_rectangle([BAR_LEFT, by, BAR_LEFT + BAR_W, by + BAR_H],
                             radius=3, fill=_RULE)
        # Bar fill
        fw = max(int(BAR_W * sc / 10), 0)
        if fw:
            d.rounded_rectangle([BAR_LEFT, by, BAR_LEFT + fw, by + BAR_H],
                                 radius=3, fill=_score_color(sc))
        d.text((BAR_LEFT + BAR_W + 8, by - 1), f"{sc}/10", font=f_bar, fill=_DARK)

    # ── Divider ──────────────────────────────────────────────────────────────
    OBS_Y = 346
    d.line([16, OBS_Y, W - 16, OBS_Y], fill=_RULE, width=1)

    # ── Observations ─────────────────────────────────────────────────────────
    d.text((20, OBS_Y + 8), "Observations", font=f_bar, fill=_MED)
    ny = OBS_Y + 28
    for note in notes[:5]:
        if ny > H - 36:
            break
        d.text((28, ny), f"• {note}", font=f_note, fill=_DARK)
        ny += 18

    # ── Footer ───────────────────────────────────────────────────────────────
    d.rectangle([0, H - 28, W, H], fill=_HEADER)
    d.text((20, H - 19),
           "Generated by opama Card Grader  ·  Estimates only — not a professional grade",
           font=f_tiny, fill=_LIGHT)

    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()
