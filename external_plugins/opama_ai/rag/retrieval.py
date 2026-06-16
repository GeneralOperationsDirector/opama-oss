# app/ai/retrieval.py
"""
Hybrid retrieval utilities (Chroma semantic + optional keyword/BM25 + cross-encoder rerank)

Exports:
- chroma_semantic(query, where, k=64) -> List[dict]
- sql_keyword(db, query, limit=128)   -> Dict[str, float]
- blend(query, deck_types, db, k=24)  -> List[dict] ranked by blended score
- blend_and_rerank(query, deck_types, db, k=24, pool=96, use_reranker=None) -> List[dict]

Design:
- Semantic (Chroma): smaller distance = better → invert & normalize to [0,1].
- Keyword (BM25): smaller score = better → invert & normalize to [0,1].
- Blend: 0.7*semantic + 0.3*keyword.
- Rerank (FlagEmbedding cross-encoder): blend top `pool`, then cross-encode and
  combine: final = 0.5*blend + 0.5*re_score (0..1). Returns top `k`.

Assumptions:
- Chroma collection `_cards` is initialized in app.ai.rag and uses a distance
  metric where lower = closer (e.g., cosine distance, not similarity).
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional
import os
from .rag import _cards  # chroma collection

# -------------------- Existing functions (unchanged) ------------------------


def chroma_semantic(
    query: str, where: Optional[dict] | None, k: int = 64
) -> List[Dict[str, Any]]:
    """
    Semantic retrieval from Chroma.

    Returns a list of dicts with:
      - id:      document id
      - doc:     stored document text
      - meta:    stored metadata
      - sem_score: raw distance from Chroma (lower is better)

    Notes:
      * We read `res["distances"]` (not `embeddings` nor `scores`), so we later
        invert/normalize to map "lower distance → higher normalized score".
      * `where` can filter by metadata (e.g., {"series": "sv3"}).
    """
    if not _cards or not query:
        return []
    res = _cards.query(query_texts=[query], n_results=int(k), where=where or {})

    # NOTE: Chroma returns lists per query; we use the 0th since we pass one query.
    # TODO: Consider try/except to guard against missing keys/shape drift in Chroma.
    return [
        {"id": i, "doc": d, "meta": m, "sem_score": s}
        for i, d, m, s in zip(
            res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]
        )
    ]


def sql_keyword(db, query: str, limit: int = 128) -> Dict[str, float]:
    """
    Keyword side-channel retrieval via SQLite FTS5 BM25.

    Returns:
      { doc_id: bm25_score } where lower bm25 is better.

    Implementation notes:
      * Expects an FTS5 virtual table `cards_fts` and bm25(cards_fts) available.
      * `MATCH ?` expects a valid FTS query string; caller should provide
        correctly quoted terms/phrases if needed.
    """
    try:
        rows = db.fetch_all(
            """
            SELECT c.id, bm25(cards_fts) AS bm25
            FROM cards_fts c
            WHERE cards_fts MATCH ?
            ORDER BY bm25
            LIMIT ?
            """,
            (query, limit),
        )
    except Exception:
        # NOTE: Fail-soft: if FTS table or function isn't available, we ignore keywords.
        return {}
    # Cast to float for consistency; some drivers return Decimal.
    return {r["id"]: float(r["bm25"]) for r in rows}


def blend(query: str, deck_types: List[str], db, k: int = 24) -> List[Dict[str, Any]]:
    """
    Blend semantic (Chroma) and keyword (FTS/BM25) signals into a single score.

    Scoring:
      sem_n = inverted-normalized(sem_score) ∈ [0,1]  # lower distance → higher sem_n
      kw_n  = inverted-normalized(bm25)      ∈ [0,1]  # lower bm25 → higher kw_n
      blend = 0.7 * sem_n + 0.3 * kw_n

    Returns top `k` by `blend`.
    """
    # Build a Chroma metadata filter if deck_types are provided.
    where = None
    if deck_types:
        # NOTE: $contains on array metadata "types" for each requested deck type.
        where = {"$or": [{"types": {"$contains": t}} for t in deck_types]}

    # Retrieve a larger set for better normalization then trim to k.
    sem = chroma_semantic(query, where, k=96)
    kw = sql_keyword(db, query, limit=256) if db is not None else {}

    # --- Normalize semantic distances into [0,1] (higher = better) ---
    sem_scores = [x["sem_score"] for x in sem]
    if sem_scores:
        hi, lo = max(sem_scores), min(sem_scores)
        rng = max(1e-6, (hi - lo))  # avoid div-by-zero if all distances equal
        for x in sem:
            # Invert so smaller distance → larger normalized score
            x["sem_n"] = (hi - x["sem_score"]) / rng
    else:
        # If we have no semantic scores at all, give a neutral mid score
        for x in sem:
            x["sem_n"] = 0.5

    # --- Normalize BM25 into [0,1] (higher = better) ---
    if kw:
        vals = list(kw.values())
        hi, lo = max(vals), min(vals)
        rng = max(1e-6, (hi - lo))

        def kw_n(v: float) -> float:
            # Invert so smaller bm25 → larger normalized score
            return (hi - v) / rng

    else:
        # No keyword channel; treat as zero contribution consistently.
        def kw_n(_: float) -> float:
            return 0.0

    # Blend weights (fixed as per design)
    w_sem, w_kw = 0.7, 0.3
    for x in sem:
        # Use 0.0 if this id didn't show up in keyword results
        x["kw_n"] = kw_n(kw.get(x["id"], 0.0))
        x["blend"] = w_sem * x["sem_n"] + w_kw * x["kw_n"]

    # Sort descending by blend and return top-k slice
    sem.sort(key=lambda x: x["blend"], reverse=True)
    return sem[:k]

    # NOTE: Potential improvements (non-breaking if added later):
    # - Clamp upstream scores to [0,1] after normalization.
    # - De-duplicate by `id` if Chroma returns near-duplicates.
    # - Log timing/telemetry for observability.


# -------------------- New: blend + cross-encoder rerank ---------------------

# Default toggle via env; None lets you override per-call.
_RERANK_DEFAULT = os.getenv("RERANK_ENABLED", "true").strip().lower() in (
    "1",
    "true",
    "yes",
    "y",
)


def blend_and_rerank(
    query: str,
    deck_types: List[str],
    db,
    k: int = 24,
    pool: int = 96,
    use_reranker: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    """
    End-to-end retrieval:
      1) Hybrid blend to get a high-recall pool (`pool`)
      2) Cross-encoder rerank (if enabled/available)
      3) Return top `k`

    Args:
      query: user query (often augmented with deck context).
      deck_types: e.g., ["Water","Lightning"] to bias semantic retrieval.
      db: handle for optional FTS5 keyword side-channel (may be None).
      k: final number of results to return.
      pool: how many blended candidates to send to reranker.
      use_reranker: override env default (True/False). None → use env.

    Returns: candidates enriched with 're_score' and 'final' when reranking runs.

    Behavior:
      * If reranker is disabled or unavailable, returns the blended top-k.
      * If enabled, ranks up to `pool` blended items with a cross-encoder and
        returns the top-k by the reranker's final score.
    """
    # NOTE: `islice` import below is unused; keeping file behavior intact.
    # TODO: Remove unused import when convenient.
    from itertools import islice  # noqa: F401

    # --- Rebuild a blended pool locally (parallel to `blend`) ---
    # We recompute here to avoid modifying the `blend` API. This also lets us
    # oversample (pool*2) semantically and widen keyword matches (pool*4).
    where = None
    if deck_types:
        where = {"$or": [{"types": {"$contains": t}} for t in deck_types]}
    sem = chroma_semantic(query, where, k=pool * 2)  # oversample for normalization
    kw = sql_keyword(db, query, limit=pool * 4) if db is not None else {}

    # --- Normalize semantic distances into [0,1] (higher = better) ---
    sem_scores = [x["sem_score"] for x in sem]
    if sem_scores:
        hi, lo = max(sem_scores), min(sem_scores)
        rng = max(1e-6, (hi - lo))
        for x in sem:
            x["sem_n"] = (hi - x["sem_score"]) / rng
    else:
        for x in sem:
            x["sem_n"] = 0.5

    # --- Normalize BM25 into [0,1] (higher = better) ---
    if kw:
        vals = list(kw.values())
        hi, lo = max(vals), min(vals)
        rng = max(1e-6, (hi - lo))

        def kw_n(v: float) -> float:
            return (hi - v) / rng

    else:

        def kw_n(_: float) -> float:
            return 0.0

    # Blend as before
    w_sem, w_kw = 0.7, 0.3
    for x in sem:
        x["kw_n"] = kw_n(kw.get(x["id"], 0.0))
        x["blend"] = w_sem * x["sem_n"] + w_kw * x["kw_n"]

    blended_pool = sorted(sem, key=lambda x: x["blend"], reverse=True)[: max(k, pool)]

    # --- Optional cross-encoder rerank ---
    enabled = _RERANK_DEFAULT if use_reranker is None else bool(use_reranker)
    if not enabled:
        # Reranking disabled → return blended pool’s top-k
        return blended_pool[:k]

    try:
        from .rerank import rerank as _ce_rerank
    except Exception:
        # NOTE: Fail-soft: if the reranker import fails, keep the blended results.
        return blended_pool[:k]

    # Cross-encode and return top-k by final score
    reranked = _ce_rerank(query, blended_pool, top_k=max(1, k))
    return reranked[:k]


# --------------------------- Improvement ideas ------------------------------
# NOTE: Consider exposing weights via env:
#   RETRIEVAL_W_SEM=0.7, RETRIEVAL_W_KW=0.3
#   RERANK_PRIOR_WEIGHT=0.5 (to match reranker's blend in app/ai/rerank.py)
#
# TODO: Deduplicate pool by 'id' before rerank to avoid wasted CE compute.
# TODO: Add truncation of very long `doc` text (token or char cap) pre-CE scoring.
# TODO: Add logging/metrics (query time, pool sizes, device info) for observability.
# TODO: Provide a helper that builds safer FTS queries (escaping/quoting terms).
# TODO: If bm25 variance is ~0 (rng≈0), consider setting kw_n=0.5 for stability.
# TODO: Allow deck_types to also narrow keyword side-channel (JOIN/WHERE id IN ...).
