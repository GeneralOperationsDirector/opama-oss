"""
Re-export shim — the LLM provider abstraction moved to
`services.shared.llm` so it can be shared with `ai_assistant`'s tool-calling
chat loop. Kept here so `chat_router.py` / `suggest_router.py` (which import
via `from .providers import ...`) need no changes.
"""

from services.shared.llm import (
    LLMMessage,
    LLMProvider,
    LLMProviderError,
    LLMResult,
    ToolCall,
    ToolSpec,
    get_provider,
    parse_json_loose,
    with_json_instruction,
)

__all__ = [
    "LLMMessage",
    "LLMProvider",
    "LLMProviderError",
    "LLMResult",
    "ToolCall",
    "ToolSpec",
    "get_provider",
    "parse_json_loose",
    "with_json_instruction",
]
