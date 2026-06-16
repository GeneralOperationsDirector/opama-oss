import os
from typing import List, Optional

from openai import OpenAI

from .base import LLMMessage, LLMProvider, LLMProviderError, LLMResult, ToolSpec, with_json_instruction
from .openai_provider import OpenAIProvider


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
        tools: Optional[List[ToolSpec]] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResult:
        model = model or self.default_model
        oai_messages = OpenAIProvider._to_openai_messages(messages)
        oai_tools = OpenAIProvider._to_openai_tools(tools)
        kwargs = {}
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        try:
            try:
                resp = self._client.chat.completions.create(
                    model=model,
                    temperature=temperature,
                    messages=oai_messages,
                    **({"tools": oai_tools} if oai_tools else {}),
                    **kwargs,
                )
            except Exception:
                if not oai_tools:
                    raise
                # Model may not support tool-calling — degrade to plain chat
                # so local-only users stay functional.
                resp = self._client.chat.completions.create(
                    model=model,
                    temperature=temperature,
                    messages=oai_messages,
                    **kwargs,
                )
        except Exception as e:
            raise LLMProviderError(f"Ollama chat error: {e}") from e
        message = resp.choices[0].message
        return LLMResult(
            content=(message.content or "").strip(),
            model=model,
            usage=self._usage(resp),
            tool_calls=OpenAIProvider._tool_calls(message),
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
