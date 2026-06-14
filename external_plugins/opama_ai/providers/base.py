"""
LLM provider abstraction.

Every AI call site in opama (`/ai/chat`, `/suggest/chat`, `/suggest/ai`)
talks to a model through this interface instead of an SDK directly. Adding a
new provider (Gemini, Grok, IBM Watson, ...) means adding one adapter module
that implements `LLMProvider` — see `openai_provider.py`,
`anthropic_provider.py`, and `ollama_provider.py` for worked examples.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

JSON_INSTRUCTION = "Respond with valid JSON only, no prose or code fences."


@dataclass
class LLMMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class LLMResult:
    content: str
    model: str
    usage: Optional[Dict[str, Any]] = None


class LLMProviderError(RuntimeError):
    """Raised when a provider isn't configured, or an upstream call fails."""


class LLMProvider(ABC):
    name: str
    default_model: str

    @abstractmethod
    def chat(
        self,
        messages: List[LLMMessage],
        *,
        model: Optional[str] = None,
        temperature: float = 0.3,
    ) -> LLMResult:
        """Plain chat completion."""

    @abstractmethod
    def chat_json(
        self,
        messages: List[LLMMessage],
        *,
        model: Optional[str] = None,
        temperature: float = 0.3,
    ) -> LLMResult:
        """
        Chat completion where the caller expects the reply content to be a
        JSON object (as a string). Providers with native JSON-mode support
        enable it; others append an instruction asking for JSON-only output.
        Use `parse_json_loose()` on `result.content` to parse either case.
        """


def with_json_instruction(
    messages: List[LLMMessage], instruction: str = JSON_INSTRUCTION
) -> List[LLMMessage]:
    """
    Merge a JSON-only instruction into the leading system message (or insert
    one if there isn't one yet). Used by providers without a native JSON
    mode. Appending a *trailing* system message instead can confuse chat
    templates that expect system messages to come first — some local models
    (e.g. Ollama's llama3.2) respond with empty content if a system message
    follows a user message.
    """
    if messages and messages[0].role == "system":
        merged = LLMMessage(
            role="system", content=f"{messages[0].content}\n\n{instruction}"
        )
        return [merged, *messages[1:]]
    return [LLMMessage(role="system", content=instruction), *messages]


def parse_json_loose(content: str) -> Any:
    """
    Parse JSON from `content`, tolerating models that wrap it in prose or
    code fences. Tries a strict parse first, then falls back to slicing from
    the first `{` to the last `}`. Returns whatever JSON value is found
    (typically a dict, but some models return a bare list).

    Raises `json.JSONDecodeError` if no valid JSON can be found.
    """
    content = content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start, end = content.find("{"), content.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(content[start : end + 1])
        raise
