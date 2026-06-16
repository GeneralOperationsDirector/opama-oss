# app/ai/rerank.py
"""
Cross-encoder reranking (FlagEmbedding)

Purpose
- Take a list of candidate docs (typically from hybrid retrieval)
- Score each candidate against the query with a cross-encoder
- Blend cross-encoder score with the previous `blend` score for stability
- Return the top_k candidates sorted by final score

Public API
    rerank(query: str, candidates: list[dict], top_k: int = 16) -> list[dict]

Expected candidate shape
    {
      "id": "...",
      "doc": "full text to score",   # falls back to 'text' or 'snippet' if absent
      "blend": 0.0..1.0              # optional prior score from retriever
      ... (any other fields you carry along)
    }

Env (optional)
    RERANKER_MODEL=BAAI/bge-reranker-v2-m3
    RERANKER_USE_FP16=true
    RERANKER_BATCH=32
"""

from __future__ import annotations
from typing import List, Dict, Any
import os

try:
    # External dependency; import guarded so the app keeps working even if missing.
    from FlagEmbedding import FlagReranker  # pip install FlagEmbedding
except Exception:  # pragma: no cover
    FlagReranker = None  # type: ignore

# ----------------------------- Config ---------------------------------------
# Model + runtime knobs via env for flexibility in different deployments.

MODEL_NAME = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")

# Accept a variety of truthy values; defaults to true (safe on modern GPUs/CPU).
USE_FP16 = os.getenv("RERANKER_USE_FP16", "true").strip().lower() in (
    "1",
    "true",
    "yes",
    "y",
)

# Batch size used by FlagEmbedding for compute_score; guarded to be >= 1.
BATCH = max(1, int(os.getenv("RERANKER_BATCH", "32")))

# NOTE: Consider adding an env to tune the prior-vs-cross weight without code change:
#   RERANK_PRIOR_WEIGHT=0.5  (then final = w * prior + (1 - w) * re_score)
# Keeping behavior unchanged here; just a suggestion.

# ----------------------- Lazy singleton instance ----------------------------
# We keep a module-level singleton to avoid paying model init cost repeatedly.

_reranker = None  # type: ignore[var-annotated]


def _get_reranker():
    """
    Lazily construct the FlagEmbedding reranker. If the library isn't installed,
    we return None and `rerank` will fall back to prior scores.

    Returns
    -------
    FlagReranker | None
        An initialized reranker instance or None if unavailable.
    """
    global _reranker
    if _reranker is not None:
        return _reranker
    if FlagReranker is None:
        # Library not present; gracefully degrade downstream.
        return None

    # NOTE: FlagReranker auto-selects CUDA if available.
    # If you need to force device, FlagEmbedding supports device="cuda"/"cpu".
    _reranker = FlagReranker(MODEL_NAME, use_fp16=USE_FP16)
    return _reranker


# -------------------------------- API ---------------------------------------


def rerank(
    query: str, candidates: List[Dict[str, Any]], top_k: int = 16
) -> List[Dict[str, Any]]:
    """
    Re-rank `candidates` against `query` with a cross-encoder and return top_k.

    Scoring:
        - re_score: cross-encoder score normalized to 0..1
        - final: 0.5 * (prior blend or 0) + 0.5 * re_score

    Side effects:
        - Mutates each candidate dict to include 're_score' and 'final'.
        - Sorts the input list in place (preserving original object identities).

    Parameters
    ----------
    query : str
        The user query / prompt used to score each candidate document.
    candidates : list[dict]
        A list of candidate objects; each should carry text under 'doc' (or
        'text' / 'snippet' fallback) and may include a prior 'blend' score.
    top_k : int, default 16
        How many results to return after sorting by final score.

    Returns
    -------
    list[dict]
        The top_k candidates (slice of the original list) sorted by 'final'.
    """
    if not candidates or not query:
        # Early out if there's nothing to rank or query is empty.
        # NOTE: This preserves behavior of returning up to `top_k` from input.
        return candidates[: max(0, top_k)]

    # Build (query, doc) pairs; tolerate different candidate text keys
    def text_of(c: Dict[str, Any]) -> str:
        # NOTE: You might want to truncate extremely long docs to protect latency
        # and memory (e.g., first N tokens/chars). Leaving behavior unchanged.
        return str(c.get("doc") or c.get("text") or c.get("snippet") or "")

    pairs = [[query, text_of(c)] for c in candidates]

    rr = _get_reranker()
    if rr is None:
        # Fallback: no cross-encoder available. Use prior `blend` if present.
        # NOTE: This makes the component no-op but stable when dependency absent.
        for c in candidates:
            prior = float(c.get("blend") or 0.0)
            c["re_score"] = 0.0
            c["final"] = prior
        candidates.sort(key=lambda x: float(x.get("final") or 0.0), reverse=True)
        # NOTE: The current behavior returns at least one item even if top_k == 0.
        # If you prefer strict top_k semantics, consider slicing [: max(0, top_k)].
        return candidates[: max(1, top_k)]

    # Compute normalized scores; FlagEmbedding returns [-1..1] when normalize=True
    try:
        scores = rr.compute_score(pairs, batch_size=BATCH, normalize=True)
    except TypeError:
        # Older versions may not support batch_size; fall back without it
        scores = rr.compute_score(pairs, normalize=True)

    # NOTE: Defensive check in case a backend returns fewer scores than inputs.
    # Leaving behavior unchanged, but if needed:
    #   if len(scores) != len(candidates): handle mismatch (log/raise/fill).

    # Blend with previous score for stability
    for c, s in zip(candidates, scores):
        # Normalize [-1, 1] -> [0, 1]
        re_norm = (float(s) + 1.0) / 2.0
        prior = float(c.get("blend") or 0.0)
        c["re_score"] = re_norm
        c["final"] = 0.5 * prior + 0.5 * re_norm

        # NOTE: If you want to expose raw cross-encoder score as well:
        #   c["re_raw"] = float(s)

    # Sort in place by the combined score
    candidates.sort(key=lambda x: float(x.get("final") or 0.0), reverse=True)

    # Return the top slice. Current behavior returns at least one item even if top_k == 0.
    return candidates[: max(1, top_k)]


# --------------------------- Additional Notes -------------------------------
# TODO: Add optional text pre-processing (e.g., truncation by tokens for latency).
# TODO: Add logging hooks (timings, device info, model name) for observability.
# TODO: Add an optional `prior_weight` parameter/env to tune blend at runtime.
# TODO: Consider de-duplication by candidate 'id' before scoring if upstream can emit dupes.
# TODO: Consider handling empty/blank text docs by skipping scoring those items to save compute.
# TODO: If you rely on `blend` heavily, clamp it to [0,1] to avoid upstream out-of-range values.
