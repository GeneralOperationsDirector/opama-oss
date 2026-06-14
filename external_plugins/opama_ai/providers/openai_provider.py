import os
from typing import List, Optional

from openai import OpenAI

from .base import LLMMessage, LLMProvider, LLMProviderError, LLMResult


class OpenAIProvider(LLMProvider):
    name = "openai"
    default_model = "gpt-4o-mini"

    def __init__(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPEN_API_KEY")
        if not api_key:
            raise LLMProviderError(
                "OpenAI provider not configured (missing OPENAI_API_KEY)."
            )
        self._client = OpenAI(api_key=api_key)

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
            raise LLMProviderError(f"OpenAI chat error: {e}") from e
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
        model = model or self.default_model
        try:
            resp = self._client.chat.completions.create(
                model=model,
                temperature=temperature,
                response_format={"type": "json_object"},
                messages=[{"role": m.role, "content": m.content} for m in messages],
            )
        except Exception as e:
            raise LLMProviderError(f"OpenAI chat error: {e}") from e
        return LLMResult(
            content=(resp.choices[0].message.content or "{}").strip(),
            model=model,
            usage=self._usage(resp),
        )
