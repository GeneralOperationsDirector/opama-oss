#!/usr/bin/env python3
# scripts/ingest_cards.py
"""
Ingest card data from the API into a Chroma collection with Ollama embeddings.

Pipeline
1) Page through `GET /cards/export` using the cursor (`next`) until exhausted.
2) Serialize each card into a compact text document for embedding.
3) Build embeddings via Ollama's `/api/embeddings` endpoint.
4) Upsert into a persistent Chroma collection (idempotent).

Design notes
- Keeps your existing env-driven configuration & defaults.
- Idempotent: `upsert` ensures safe re-runs; `RESET=1` drops the collection first.
- Defensive: exponential backoff with jitter for fetches; chunked upserts; clear logs.
- Embeddings: simple per-doc POST requests (batch windowing, but not parallelized
  to keep things predictable). You can scale later if needed.

Env
  API_BASE=http://localhost:8008
  INGEST_PAGE_LIMIT=5000
  INGEST_MAX_RETRIES=5
  RESET=0                    # set 1 to drop+recreate the collection
  OLLAMA_URL=http://localhost:11434
  EMBED_MODEL=nomic-embed-text
  CHROMA_PATH=var/chroma
  CHROMA_COLLECTION=ptcg_cards
  CHROMA_BATCH=256           # upsert batch size
  BACKOFF_JITTER=1           # add small random jitter to retries
  DRY_RUN=0                  # set 1 to test fetch/serialize without writing
"""

from __future__ import annotations
import os, httpx, asyncio, aiohttp, pathlib, random, sys
from typing import Optional, Tuple, List, Dict, Any
import chromadb
from chromadb.api.types import EmbeddingFunction

# ---- Env (typed, with reasonable defaults) ---------------------------------
API_BASE = os.getenv("API_BASE", "http://localhost:8008").rstrip("/")
PAGE_LIMIT = int(os.getenv("INGEST_PAGE_LIMIT", "5000"))
MAX_RETRIES = int(os.getenv("INGEST_MAX_RETRIES", "5"))
RESET = os.getenv("RESET", "0") == "1"

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")

CHROMA_PATH = os.getenv("CHROMA_PATH", "var/chroma")
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "ptcg_cards")
UPSERT_BATCH = int(os.getenv("CHROMA_BATCH", "256"))

BACKOFF_JITTER = os.getenv("BACKOFF_JITTER", "1") == "1"
DRY_RUN = os.getenv("DRY_RUN", "0") == "1"

TIMEOUT = aiohttp.ClientTimeout(  # generous read time—embedding & IO can be slow
    total=None,
    connect=30,
    sock_connect=30,
    sock_read=600,
)


def backoff(attempt: int) -> float:
    """Exponential backoff with an optional small jitter (max 30s)."""
    base = min(30.0, 2.0**attempt)
    return base + (random.random() * 0.5 if BACKOFF_JITTER else 0.0)


# ---------- Fetch cards via cursor pagination ----------
async def fetch_page(
    session: aiohttp.ClientSession, cursor: Optional[str]
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Fetch a page from /cards/export with optional cursor.

    Returns:
        (items, next_cursor)
    """
    params = {"limit": str(PAGE_LIMIT)}
    if cursor:
        params["cursor"] = cursor
    for attempt in range(MAX_RETRIES):
        try:
            async with session.get(f"{API_BASE}/cards/export", params=params) as r:
                r.raise_for_status()
                data = await r.json()
                return data.get("items", []), data.get("next")
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                raise
            sleep = backoff(attempt)
            print(f"[fetch] retry {attempt+1}/{MAX_RETRIES} in {sleep:.1f}s: {e}")
            await asyncio.sleep(sleep)


async def fetch_all_cards() -> List[Dict[str, Any]]:
    """
    Page through the entire export until `next` is None.
    """
    out: List[Dict[str, Any]] = []
    cursor = None
    async with aiohttp.ClientSession(timeout=TIMEOUT) as s:
        while True:
            batch, cursor = await fetch_page(s, cursor)
            if not batch:
                break
            out.extend(batch)
            print(f"[fetch] got {len(batch):>5} (total {len(out)}) next={cursor}")
            if not cursor:
                break
    return out


# ---------- Serialize a card to a compact text doc ----------
def _to_str_list(v) -> List[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [x.strip() for x in v.split(",") if x.strip()]
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v if str(x).strip()]
    return [str(v)]


def serialize_card(row: dict) -> str:
    """
    Turn a card row into a compact, human-readable text block for embedding.
    Keep this stable; changing this string affects embeddings & recall.
    """
    name = row.get("name") or ""
    set_id = row.get("set_id") or ""
    number = row.get("number") or ""
    types = ", ".join(_to_str_list(row.get("types")))
    subtypes = ", ".join(_to_str_list(row.get("subtypes")))
    rarity = (row.get("rarity") or "").strip()

    parts = [
        f"{name} • {set_id} #{number}".strip(" •#"),
        f"Types: {types}" if types else "",
        f"Subtypes: {subtypes}" if subtypes else "",
        f"Rarity: {rarity}" if rarity else "",
    ]

    abil_name = (row.get("ability_name") or "").strip()
    abil_text = (row.get("ability_text") or "").strip()
    if abil_name or abil_text:
        parts.append(f"Ability — {abil_name}: {abil_text}".strip())

    for i in (1, 2, 3):
        n = (row.get(f"attack{i}_name") or "").strip()
        d = (row.get(f"attack{i}_damage") or "").strip()
        t = (row.get(f"attack{i}_text") or "").strip()
        if n or d or t:
            parts.append(f"Attack {i} — {n} {d}: {t}".strip())

    extra = []
    if row.get("hp"):
        extra.append(f"HP {row['hp']}")
    if row.get("retreat_cost") is not None:
        extra.append(f"Retreat {row['retreat_cost']}")
    if row.get("weakness"):
        extra.append(f"Weakness {row['weakness']}")
    if row.get("resistance"):
        extra.append(f"Resistance {row['resistance']}")
    if extra:
        parts.append(" / ".join(extra))

    return "\n".join(p for p in parts if p)


# ---------- Ollama embedding function ----------
class OllamaEF(EmbeddingFunction):
    """
    Chroma EmbeddingFunction adapter for Ollama's /api/embeddings endpoint.
    """

    def __init__(
        self,
        model: str = EMBED_MODEL,
        url: str = OLLAMA_URL,
        timeout: float = 120.0,
        batch: int = 32,
    ):
        self.model = model
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.batch = max(1, int(batch))

    def _embed_one(self, client: httpx.Client, text: str) -> List[float]:
        """
        Call Ollama once for a single text and return the embedding vector.
        """
        resp = client.post(
            f"{self.url}/api/embeddings",
            json={"model": self.model, "prompt": text},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        emb = data.get("embedding")
        if not isinstance(emb, list):
            raise RuntimeError(f"Unexpected embeddings payload from Ollama: {data}")
        return emb

    def __call__(self, input_texts: List[str]) -> List[List[float]]:
        """
        Produce embeddings for a list of texts.
        Batches are processed sequentially to keep memory + CPU predictable.
        """
        out: List[List[float]] = []
        if not input_texts:
            return out
        with httpx.Client() as client:
            for i in range(0, len(input_texts), self.batch):
                chunk = input_texts[i : i + self.batch]
                for text in chunk:
                    out.append(self._embed_one(client, text))
        return out


# ---------- Main ----------
async def main():
    # Ensure Chroma path exists
    pathlib.Path(CHROMA_PATH).mkdir(parents=True, exist_ok=True)

    # 1) Fetch cards
    cards = await fetch_all_cards()
    print(f"[ingest] total cards fetched: {len(cards)}")

    if DRY_RUN:
        print("[ingest] DRY_RUN=1 — skipping write to Chroma")
        return

    # 2) Open Chroma
    client = chromadb.PersistentClient(path=CHROMA_PATH)

    if RESET:
        try:
            client.delete_collection(COLLECTION_NAME)
            print(f"[ingest] deleted collection {COLLECTION_NAME}")
        except Exception as e:
            print(f"[ingest] (reset) delete failed or not present: {e}")

    col = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=OllamaEF(),
        metadata={"hnsw:space": "ip"},  # inner product
    )

    # 3) Build ids, docs, metadata (stable schema)
    ids: List[str] = []
    docs: List[str] = []
    metas: List[Dict[str, Any]] = []
    for c in cards:
        cid = str(c["id"])
        ids.append(cid)
        docs.append(serialize_card(c))
        metas.append(
            {
                "name": c.get("name"),
                "set_id": c.get("set_id"),
                "types": ", ".join(_to_str_list(c.get("types"))),
                "supertype": c.get("supertype"),
                "rarity": c.get("rarity"),
                "number": c.get("number"),
            }
        )

    # 4) Ingest (chunked). Prefer upsert so re-runs are idempotent.
    B = max(1, int(UPSERT_BATCH))
    total = len(ids)
    print(f"[ingest] writing to collection={COLLECTION_NAME} (batch={B}) …")

    for i in range(0, total, B):
        _ids = ids[i : i + B]
        _docs = docs[i : i + B]
        _metas = metas[i : i + B]
        try:
            col.upsert(ids=_ids, documents=_docs, metadatas=_metas)
            print(f"[ingest] upserted {i + len(_ids):>6} / {total}")
        except Exception as e:
            # Log and continue; a later re-run will fix partial failures.
            print(f"[ingest] upsert failed at {i}-{i+len(_ids)}: {e}", file=sys.stderr)

    print(f"✅ Ingested {total} cards into {CHROMA_PATH}/{COLLECTION_NAME}")


if __name__ == "__main__":
    asyncio.run(main())

