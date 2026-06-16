"""
Card identification — local-only hybrid pipeline.

Three extraction strategies run in sequence and their results are fused:

  1. Ollama full-image  — sends the whole card to the best available local
                          vision model. Extracts name, number, set, type.
  2. Ollama region-crop — OpenCV crops the bottom-right corner (where the
                          card number lives), sends just that patch. More
                          focused → higher accuracy for the number.
  3. Tesseract OCR      — deterministic, instant, zero AI cost. Used when
                          the `tesseract` binary is present. Extracts the
                          number via regex on the bottom-corner crop.

Fusion rules:
  • Number  : region-crop wins → tesseract → full-image (most specific first)
  • Name    : full-image wins → tesseract fallback
  • Set     : full-image only
  • Confidence : "high" if two+ providers agree on number AND name,
                 "medium" if at least one got each field,
                 "low" otherwise

All ExtractionResult objects are returned alongside the fused result so the
router can store them as IdentificationAttempt rows. User corrections during
the transfer step become ground truth that feeds the per-provider accuracy stats.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

# Ordered list of vision models to try. Override in .env.local.
# Only models that support image input will work (text-only models are skipped).
_DEFAULT_MODELS = "llama3.2-vision,minicpm-v,llava,moondream"
OLLAMA_VISION_MODELS: list[str] = [
    m.strip()
    for m in os.getenv("OLLAMA_VISION_MODELS", _DEFAULT_MODELS).split(",")
    if m.strip()
]

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ExtractionResult:
    """Raw output from a single extraction provider."""
    provider: str            # e.g. "ollama:llama3.2-vision", "ocr_tesseract"
    name: Optional[str] = None
    number: Optional[str] = None      # as printed, e.g. "049/091"
    set_name: Optional[str] = None
    card_number: Optional[str] = None  # leading-zero-stripped, e.g. "49"
    set_total: Optional[str] = None    # e.g. "91"
    confidence: str = "low"


@dataclass
class CardIdentification:
    """Fused result from all providers, ready for catalog lookup."""
    name: Optional[str] = None
    number: Optional[str] = None
    set_name: Optional[str] = None
    hp: Optional[str] = None
    card_type: Optional[str] = None
    confidence: str = "low"
    card_number: Optional[str] = None
    set_total: Optional[str] = None

    # Filled by router after catalog lookup
    catalog_card_id: Optional[str] = None
    catalog_set_id: Optional[str] = None
    catalog_match: bool = False

    # All provider results — stored as IdentificationAttempt rows
    provider_results: list[ExtractionResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def identify_card(image_bytes: bytes) -> Optional[CardIdentification]:
    """
    Run the hybrid extraction pipeline on a card image.
    Returns None only if every strategy fails entirely.
    """
    results: list[ExtractionResult] = []

    # 1. Ollama full-image (contextual understanding)
    full = _try_ollama_full(image_bytes)
    if full:
        results.append(full)

    # 2. Ollama region-crop (number-focused)
    crop_bytes = _crop_number_region(image_bytes)
    if crop_bytes:
        region = _try_ollama_region(crop_bytes)
        if region:
            results.append(region)

    # 3. Tesseract OCR (deterministic, if binary available)
    ocr = _try_tesseract(crop_bytes or image_bytes)
    if ocr:
        results.append(ocr)

    if not results:
        log.warning("All identification strategies failed")
        return None

    return _fuse(results)


# ---------------------------------------------------------------------------
# Strategy 1: Ollama full-image
# ---------------------------------------------------------------------------

_FULL_PROMPT = """\
You are reading a trading card image. Extract only what is literally printed on the card.

Return a JSON object (nothing else — no markdown, no explanation):
{
  "name": "card name exactly as printed, or null",
  "number": "card number as printed, e.g. '049/091' or '049', or null",
  "set_name": "expansion or set name if visible, or null",
  "hp": "HP value if this is a Pokémon card, e.g. '130', or null",
  "card_type": "energy type(s) if visible, e.g. 'Fire', or null",
  "confidence": "high if most fields clearly readable, medium if some unclear, low if hard to read"
}

Only report text you can actually see."""

_REGION_PROMPT = """\
This is a close-up crop of a trading card's corner. Extract the card number printed here.

Return a JSON object (nothing else):
{
  "number": "the card number exactly as printed, e.g. '049/091', or null",
  "confidence": "high if clearly readable, low if blurry or absent"
}"""


def _try_ollama_full(image_bytes: bytes) -> Optional[ExtractionResult]:
    return _call_ollama(image_bytes, _FULL_PROMPT, provider_prefix="ollama_full")


def _try_ollama_region(crop_bytes: bytes) -> Optional[ExtractionResult]:
    return _call_ollama(crop_bytes, _REGION_PROMPT, provider_prefix="ollama_region")


def _call_ollama(
    image_bytes: bytes,
    prompt: str,
    provider_prefix: str,
) -> Optional[ExtractionResult]:
    """Try each configured Ollama vision model in order, return on first success."""
    try:
        import requests as _req
    except ImportError:
        return None

    b64 = base64.standard_b64encode(image_bytes).decode()

    for model in OLLAMA_VISION_MODELS:
        try:
            resp = _req.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt, "images": [b64]}],
                    "stream": False,
                    "options": {"temperature": 0},
                },
                timeout=20,
            )

            if resp.status_code == 404:
                log.debug("Ollama model %s not available, trying next", model)
                continue

            resp.raise_for_status()
            content = resp.json()["message"]["content"]
            result = _parse_json_response(content, f"{provider_prefix}:{model}")
            if result:
                return result

        except _req.exceptions.ConnectionError:
            log.debug("Ollama not reachable at %s", OLLAMA_URL)
            return None   # No point trying more models
        except _req.exceptions.Timeout:
            log.warning("Ollama %s timed out — skipping remaining models", model)
            return None   # If one model is too slow, the others will be too
        except Exception as exc:
            log.warning("Ollama %s failed: %s", model, exc)
            continue

    return None


# ---------------------------------------------------------------------------
# Strategy 2: OpenCV region crop (shared between Ollama region & Tesseract)
# ---------------------------------------------------------------------------

def _crop_number_region(image_bytes: bytes) -> Optional[bytes]:
    """
    Return JPEG bytes of the bottom-right corner of the card image,
    upscaled 3× for better text readability. Returns None on failure.
    """
    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return None

    h, w = img.shape[:2]
    # Bottom-right ~35% width × ~15% height — where the card number lives
    crop = img[int(h * 0.85):, int(w * 0.55):]
    if crop.size == 0:
        return None

    # Upscale for readability
    upscaled = cv2.resize(crop, (crop.shape[1] * 3, crop.shape[0] * 3),
                          interpolation=cv2.INTER_CUBIC)
    ok, buf = cv2.imencode(".jpg", upscaled, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return buf.tobytes() if ok else None


# ---------------------------------------------------------------------------
# Strategy 3: Tesseract OCR
# ---------------------------------------------------------------------------

def _try_tesseract(image_bytes: bytes) -> Optional[ExtractionResult]:
    """
    Run pytesseract on the (already-cropped) image bytes.
    Returns None if tesseract is not installed on this system.
    """
    try:
        import pytesseract
        from PIL import Image
        import io
        pytesseract.get_tesseract_version()  # raises if binary missing
    except Exception:
        return None

    try:
        pil_img = Image.open(io.BytesIO(image_bytes)).convert("L")
        text = pytesseract.image_to_string(pil_img, config="--oem 3 --psm 6")
    except Exception as exc:
        log.warning("Tesseract failed: %s", exc)
        return None

    # Look for NNN/NNN number pattern
    match = re.search(r"(\d{1,4})\s*/\s*(\d{1,4})", text.replace("\n", " "))
    if not match:
        return None

    number = f"{match.group(1)}/{match.group(2)}"
    card_number = match.group(1).lstrip("0") or "0"
    set_total = match.group(2).lstrip("0") or "0"

    return ExtractionResult(
        provider="ocr_tesseract",
        number=number,
        card_number=card_number,
        set_total=set_total,
        confidence="high",
    )


# ---------------------------------------------------------------------------
# JSON parsing helper
# ---------------------------------------------------------------------------

_NUMBER_RE = re.compile(r"(\d{1,4})\s*/\s*(\d{1,4})")


def _parse_json_response(raw: str, provider: str) -> Optional[ExtractionResult]:
    cleaned = re.sub(r"^```[a-z]*\n?", "", raw.strip()).rstrip("`").strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        log.debug("%s: JSON parse failed on: %r", provider, raw[:120])
        return None

    number_raw = data.get("number") or None
    card_number = set_total = None
    if number_raw:
        m = _NUMBER_RE.search(str(number_raw))
        if m:
            card_number = m.group(1).lstrip("0") or "0"
            set_total   = m.group(2).lstrip("0") or "0"
            number_raw  = f"{m.group(1)}/{m.group(2)}"

    return ExtractionResult(
        provider=provider,
        name=data.get("name") or None,
        number=number_raw,
        set_name=data.get("set_name") or None,
        card_number=card_number,
        set_total=set_total,
        confidence=data.get("confidence", "low"),
    )


# ---------------------------------------------------------------------------
# Fusion
# ---------------------------------------------------------------------------

def _fuse(results: list[ExtractionResult]) -> CardIdentification:
    """
    Combine all provider results into a single best-guess identification.

    Priority order:
      Number : ollama_region > ocr_tesseract > ollama_full
      Name   : ollama_full   > ocr_tesseract
      Set    : ollama_full
    """
    def _first(attr: str, priority: list[str]) -> Optional[str]:
        """Return the first non-None value from results ordered by provider prefix."""
        ordered = sorted(
            results,
            key=lambda r: next(
                (i for i, p in enumerate(priority) if r.provider.startswith(p)),
                len(priority),
            ),
        )
        for r in ordered:
            val = getattr(r, attr)
            if val:
                return val
        return None

    number_priority = ["ollama_region", "ocr_tesseract", "ollama_full"]
    name_priority   = ["ollama_full", "ocr_tesseract", "ollama_region"]

    number     = _first("number",      number_priority)
    card_num   = _first("card_number", number_priority)
    set_total  = _first("set_total",   number_priority)
    name       = _first("name",        name_priority)
    set_name   = _first("set_name",    name_priority)

    # Confidence: high if we got both name and number from at least 2 providers
    providers_with_number = sum(1 for r in results if r.number)
    providers_with_name   = sum(1 for r in results if r.name)

    if providers_with_number >= 2 and providers_with_name >= 1:
        confidence = "high"
    elif number or name:
        confidence = "medium"
    else:
        confidence = "low"

    return CardIdentification(
        name=name,
        number=number,
        set_name=set_name,
        confidence=confidence,
        card_number=card_num,
        set_total=set_total,
        provider_results=results,
    )
