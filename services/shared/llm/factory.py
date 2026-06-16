import os
from typing import Optional

from .base import LLMProvider, LLMProviderError


def get_provider(name: Optional[str] = None) -> LLMProvider:
    """
    Resolve an `LLMProvider` by name, falling back to the `AI_PROVIDER` env
    var, then "openai". Raises `LLMProviderError` if the resolved provider
    isn't configured (e.g. missing API key) or the name is unknown.
    """
    resolved = (name or os.getenv("AI_PROVIDER") or "openai").lower()

    if resolved == "openai":
        from .openai_provider import OpenAIProvider

        return OpenAIProvider()
    if resolved == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider()
    if resolved == "ollama":
        from .ollama_provider import OllamaProvider

        return OllamaProvider()

    raise LLMProviderError(f"Unknown AI_PROVIDER: {resolved!r}")
