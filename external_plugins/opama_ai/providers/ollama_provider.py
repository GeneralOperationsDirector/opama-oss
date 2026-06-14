import os
from typing import List, Optional

from openai import OpenAI

from .base import LLMMessage, LLMProvider, LLMProviderError, LLMResult, with_json_instruction


class OllamaProvider(LLMProvider):
    """
    Talks to Ollama's OpenAI-compatible endpoint (`/v1/chat/completions`),
    so it reuses the `openai` SDK with a custom base_url. No API key is
    required, so this provider never raises "not configured" — connection
    failures surface as upstream errors from `chat()`/`chat_json()`.
    """

    name = "ollama"

    def __init__(self) -> None:
        base_url = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
        self.default_model = os.getenv("OLLAMA_MODEL", "llama3.2")
        self._client = OpenAI(base_url=f"{base_url}/v1", api_key="ollama")

    def _usage(self, resp) -> Optional[dict]:
        usage = getattr(resp, "usage", None)
        if usage is None:
            return None
        return usage.model_dump() if hasattr(usage, "model_dump") else dict(usage)

    def chat(
        self,
        messages: List[LLMMessage],
        *,
        model: Optional[str] = None,
        temperature: float = 0.3,
    ) -> LLMResult:
        model = model or self.default_model
        try:
            resp = self._client.chat.completions.create(
                model=model,
                temperature=temperature,
                messages=[{"role": m.role, "content": m.content} for m in messages],
            )
        except Exception as e:
            raise LLMProviderError(f"Ollama chat error: {e}") from e
        return LLMResult(
            content=(resp.choices[0].message.content or "").strip(),
            model=model,
            usage=self._usage(resp),
        )

    def chat_json(
        self,
        messages: List[LLMMessage],
        *,
        model: Optional[str] = None,
        temperature: float = 0.3,
    ) -> LLMResult:
        # Ollama's response_format support is version-dependent — ask for
        # JSON via instruction and let the caller parse leniently.
        return self.chat(with_json_instruction(messages), model=model, temperature=temperature)
