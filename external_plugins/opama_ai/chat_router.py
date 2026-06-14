"""
AI Chat (with optional RAG)
---------------------------
This router defines the `/ai/chat` endpoint, which allows users to chat with
an LLM about Pokémon TCG decks. The endpoint can optionally augment the
conversation with Retrieval-Augmented Generation (RAG).

Pipeline:
  1) Build an OpenAI client (env-based); return 400 if not configured.
  2) If deck_id is present, hydrate a compact context from the DB.
  3) Build a retrieval query from the user's last message + deck context.
  4) Retrieve top-K card snippets (optionally filtered by primary types).
  5) Optionally compress those hits via Ollama for token savings.
  6) Inject the summarized RAG context as a *system* message.
  7) Call OpenAI and return the reply (with usage if available).

Notes:
- RAG helpers live in app.ai.rag (query, retrieval, and local compression).
- Ollama compression is best-effort; fallback is raw snippets.
- Summarized context is injected early in the system role to influence responses.
"""

from typing import List, Literal, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field
from sqlmodel import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

# RAG pipeline helpers
from .rag.rag import _deck_context, build_query, retrieve_cards, compress_with_ollama

# LLM provider abstraction (raises LLMProviderError if not configured)
from .providers import LLMMessage, LLMProviderError, get_provider

# DB session provider
from services.shared.database import get_session

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

# Register this router with FastAPI under the "/ai" prefix
router = APIRouter(prefix="/ai", tags=["ai"])

# OpenAI-compatible roles
Role = Literal["system", "user", "assistant"]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    """Represents a single OpenAI-style chat message."""

    role: Role
    content: str


class ChatRequest(BaseModel):
    """
    Chat request body accepted by the endpoint.

    Fields:
        - user_id (Optional[int]): passed for enrichment of deck context.
        - deck_id (Optional[int]): fetch deck metadata/context from DB if given.
        - model (Optional[str]): target model; defaults to the active
          provider's `default_model` when omitted.
        - temperature (float): controls randomness/creativity of responses.
        - messages (List[ChatMessage]): conversation history.
        - top_k (int): number of card snippets to retrieve (RAG).
        - summarize (bool): whether to compress retrieved snippets with Ollama.
    """

    user_id: Optional[int] = None
    deck_id: Optional[int] = None
    model: Optional[str] = None
    temperature: float = 0.3
    messages: List[ChatMessage] = Field(default_factory=list)
    top_k: int = 24
    summarize: bool = True


class ChatResponse(BaseModel):
    """
    Response payload returned by the endpoint.

    Attributes:
        - reply (str): assistant’s generated message.
        - usage (Optional[Dict]): token usage metadata (if provided by OpenAI).
    """

    reply: str
    usage: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/chat", response_model=ChatResponse)
@limiter.limit("10/minute")
def chat(
    request: Request,
    req: ChatRequest,
    session: Session = Depends(get_session)
):
    """
    Chat with the AI deck assistant, optionally augmented with RAG.

    Rate Limit: 10 requests per minute per IP (AI is expensive).

    Steps:
        1. Build OpenAI client (fail early if no API key).
        2. Optionally fetch deck context (types, metadata) from DB.
        3. Build retrieval query based on last user message + deck context.
        4. Retrieve top-K card snippets.
        5. Optionally compress snippets via Ollama (token-saving step).
        6. Inject summarized context into the system role messages.
        7. Call OpenAI chat completion and return result.

    Resilience:
        - If Ollama is down, falls back to raw truncated snippets.
        - If retrieval fails, continues with no RAG context.
        - If OpenAI fails, raises HTTP 502.
    """
    # 1) LLM provider (raise 400 if not configured)
    try:
        provider = get_provider()
    except LLMProviderError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 2) Deck context (safe retrieval; errors swallowed → empty dict)
    deck_ctx: Dict[str, Any] = {}
    if req.deck_id:
        try:
            deck_ctx = _deck_context(session, req.deck_id) or {}
        except Exception:
            deck_ctx = {}

    # 3) Build retrieval query from last user message + deck context
    user_text = req.messages[-1].content if req.messages else ""
    query = build_query(user_text, deck_ctx)
    primary_types = deck_ctx.get("types") or None

    # 4) Retrieve candidate card snippets (fail-safe to empty list)
    try:
        hits = retrieve_cards(query, primary_types, k=req.top_k)
    except Exception:
        hits = []

    # 5) Optional compression of hits with Ollama → reduce token footprint
    compressed_context = ""
    if req.summarize and hits:
        try:
            compressed_context = compress_with_ollama(
                hits,
                instruction=(
                    "Condense for Pokémon TCG strategy analysis. "
                    "Prefer speed/consistency, draw, search, and energy acceleration. "
                    "Keep card_id and name when useful."
                ),
            )
        except Exception:
            # Fallback: use a few raw/truncated snippets instead
            compressed_context = "\n".join(
                (h.get("snippet") or h.get("document") or "")[:500] for h in hits[:6]
            )

    # 6) Prepare OpenAI message payload
    messages = [m.model_dump() for m in req.messages]

    # Inject RAG system message (insert after any existing system prompt)
    if compressed_context.strip():
        rag_msg = {
            "role": "system",
            "content": (
                "Context from the card database (summarized):\n"
                f"{compressed_context}\n\n"
                "Use this context when answering. Cite cards by their [card_id] where relevant."
            ),
        }
        insert_at = 1 if (messages and messages[0].get("role") == "system") else 0
        messages.insert(insert_at, rag_msg)

    # 7) Call the LLM provider
    try:
        result = provider.chat(
            [LLMMessage(role=m["role"], content=m["content"]) for m in messages],
            model=req.model,
            temperature=req.temperature,
        )
    except LLMProviderError as e:
        # Upstream failure → 502 Bad Gateway
        raise HTTPException(status_code=502, detail=str(e))

    return ChatResponse(reply=result.content, usage=result.usage)
