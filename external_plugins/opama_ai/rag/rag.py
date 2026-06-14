# app/ai/rag.py
"""
RAG helpers (Chroma + optional Ollama compression)

Responsibilities
- Build a compact deck context from the DB (for grounding).
- Turn (user text + deck context) into a retrieval query.
- Query ChromaDB for relevant card snippets (optionally filtered by types).
- Compress retrieved snippets via a local Ollama model (best-effort).

Env
- CHROMA_PATH=var/chroma
- OLLAMA_URL=http://localhost:11434
- OLLAMA_COMPRESS_MODEL=llama3.1:8b-instruct   # any local chat model works

Notes
- All functions are small and defensive. If Chroma or Ollama are offline,
  we return empty results or raw snippets so the app still responds.

# TODO(obs): Log exceptions at debug-level in retrieval/compression paths for easier triage.
# TODO(config): Consider env for collection name (e.g., CHROMA_COLLECTION) to avoid magic strings.
# TODO(types): Align return field names with callers (see note in retrieve_cards()).
"""

from __future__ import annotations
import os
from typing import Any, Dict, List, Optional

import httpx
import chromadb
from sqlmodel import Session, select

from opama_pokemon_tcg.decks.models import DeckCard  # minimal import to avoid heavy deps
from opama_pokemon_tcg.catalog.models import Card

# --- Runtime settings --------------------------------------------------------

CHROMA_PATH = os.getenv("CHROMA_PATH", "var/chroma")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
COMPRESS_MODEL = os.getenv("OLLAMA_COMPRESS_MODEL", "llama3.1:8b-instruct")

# --- Chroma client/collection -----------------------------------------------

try:
    # Persistent client stores data under CHROMA_PATH
    _client = chromadb.PersistentClient(path=CHROMA_PATH)
    _cards = _client.get_or_create_collection("ptcg_cards")
except Exception:
    # If Chroma isn't available at runtime, retrieval will gracefully no-op.
    _client, _cards = None, None
    # NOTE: Keep this silent in prod; optionally add debug logging if desired.


# ---------------------------------------------------------------------------
# Deck context (DB -> compact JSON)
# ---------------------------------------------------------------------------


def _deck_context(session: Session, deck_id: int) -> Dict[str, Any]:
    """
    Build a compact deck context for grounding/chat:
    {
      "types": ["Water","Lightning"],
      "list": [{"card_id": "...", "qty": 2, "name": "Pikachu", "types": "Lightning"}]
    }

    - Types are derived by tallying card quantities across the deck and taking
      the top 3 by total qty.
    - Card list is intentionally minimal to control token growth.
    """
    # Load deck cards
    dcs: List[DeckCard] = session.exec(
        select(DeckCard).where(DeckCard.deck_id == deck_id)
    ).all()
    if not dcs:
        return {"types": [], "list": []}

    # Hydrate minimal card info in one round trip
    ids = list({dc.card_id for dc in dcs})
    cards = {c.id: c for c in session.exec(select(Card).where(Card.id.in_(ids))).all()}

    lines: List[Dict[str, Any]] = []
    type_counts: Dict[str, int] = {}

    for dc in dcs:
        c = cards.get(dc.card_id)
        name = (c.name if c else None) or dc.card_id
        c_types = (c.types or "") if c else ""
        lines.append(
            {
                "card_id": dc.card_id,
                "qty": int(dc.quantity or 0),
                "name": name,
                "types": c_types,
            }
        )
        # Tally types by quantity for "primary types" inference
        for t in [x.strip() for x in c_types.split(",") if x.strip()]:
            type_counts[t] = type_counts.get(t, 0) + (dc.quantity or 0)

    # Top distinct types by total qty (up to 3)
    types_sorted = sorted(type_counts.items(), key=lambda kv: kv[1], reverse=True)
    top_types = [t for t, _ in types_sorted[:3]]

    return {"types": top_types, "list": lines}


# ---------------------------------------------------------------------------
# Query construction
# ---------------------------------------------------------------------------


def build_query(user_text: str, deck_ctx: Dict[str, Any]) -> str:
    """
    Compose a retrieval query string from user text + deck context.
    Example:
      "<user text>\n\nActive deck types: Water, Lightning\nCore cards: 2x Pikachu; 4x Rare Candy; ..."
    """
    head = (user_text or "").strip()
    types = ", ".join(deck_ctx.get("types", []) or [])
    lines = (deck_ctx.get("list", []) or [])[:12]  # keep this short to reduce tokens
    core = "; ".join(
        f"{x.get('qty', 0)}x {x.get('name') or x.get('card_id')}" for x in lines
    )
    return f"{head}\n\nActive deck types: {types or 'Unknown'}\nCore cards: {core}"


# ---------------------------------------------------------------------------
# Retrieval from Chroma
# ---------------------------------------------------------------------------


def retrieve_cards(
    query: str, primary_types: Optional[List[str]], k: int = 20
) -> List[Dict[str, Any]]:
    """
    Query the 'ptcg_cards' collection for text snippets relevant to the query.

    Filtering:
    - If `primary_types` are provided, apply OR contains filter on metadata["types"].
      This relies on the collection having inserted metadata like {"types": "Fire,Water"}.

    Returns:
      A list of dictionaries with keys:
        - "id":   str  (Chroma document id, expected to be card_id)
        - "meta": dict (original metadata inserted alongside the document)
        - "text": str  (stored document/snippet text)

    # TODO(naming): Downstream code (app/routers/ai.py fallback) looks for keys
    #               "snippet" or "document". Consider returning "document"
    #               instead of "text", or adapt the caller to use "text".
    """
    if not _cards or not query:
        return []

    where = {}
    if primary_types:
        pts = [t for t in primary_types if t]
        if pts:
            where = (
                {"$or": [{"types": {"$contains": t}} for t in pts]}
                if len(pts) > 1
                else {"types": {"$contains": pts[0]}}
            )

    try:
        res = _cards.query(
            query_texts=[query],
            n_results=max(1, min(int(k), 100)),  # hard-cap to 100 for safety
            where=where,
        )
        # Chroma returns lists per query; take the first (single) query's results
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        ids = res.get("ids", [[]])[0]

        # Defensive zip (will truncate to shortest)
        return [
            {"id": i, "meta": (m or {}), "text": (d or "")}
            for i, m, d in zip(ids, metas, docs)
        ]
    except Exception:
        # Retrieval is best-effort—return empty on failures
        return []


# ---------------------------------------------------------------------------
# Compression via local Ollama (best-effort)
# ---------------------------------------------------------------------------


def compress_with_ollama(
    chunks: List[Dict[str, Any]], instruction: str, max_chars: int = 4000
) -> str:
    """
    Summarize retrieved snippets with a local model to save tokens.

    Input:
      chunks: list from `retrieve_cards()`
      instruction: short instruction biasing toward TCG strategy details
      max_chars: soft cap to limit request size to the local model

    Output:
      - A concise bullet list string on success
      - If Ollama is unavailable/errors, returns raw (truncated) combined text

    # TODO(token): Consider token-aware truncation instead of char count.
    # TODO(stream): If summaries can be long, you may stream to Ollama for responsiveness.
    """
    if not chunks:
        return ""

    # Build a compact, citeable input; include [id] and name when present
    combined = "\n\n".join(
        f"[{c.get('id')}] {(c.get('meta') or {}).get('name', '')} — {c.get('text','')}"
        for c in chunks
    )
    if len(combined) > max_chars:
        combined = combined[:max_chars]

    prompt = (
        f"{instruction}\n\n"
        "Below are card snippets. Summarize only tactics, combos, removal, speed lines. "
        "Return a concise bullet list. Include [card_id] tags for citations.\n\n"
        f"{combined}"
    )

    try:
        # Ollama chat API; keep temperature 0 for deterministic compression
        r = httpx.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": COMPRESS_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "options": {"temperature": 0.0},
            },
            timeout=120,  # generous since this is local; adjust if needed
        )
        r.raise_for_status()
        data = r.json()

        # Newer Ollama chat responses: {"message": {"content": "..."}}
        if (
            isinstance(data, dict)
            and "message" in data
            and isinstance(data["message"], dict)
            and "content" in data["message"]
        ):
            return (data["message"]["content"] or "").strip()

        # Fallback for variants: {"content": "..."}
        if isinstance(data, dict) and "content" in data:
            return (data["content"] or "").strip()

        # Unknown schema—fall back to the raw combined text
        return combined

    except Exception:
        # Best-effort: if Ollama is down/offline, return raw truncated text so the LLM can proceed.
        return combined
