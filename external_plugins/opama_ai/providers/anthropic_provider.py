import os
from typing import List, Optional

import anthropic

from .base import LLMMessage, LLMProvider, LLMProviderError, LLMResult, with_json_instruction

# Anthropic requires max_tokens; opama's call sites are short replies/JSON
# objects, not long-form generation.
_MAX_TOKENS = 1024


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    default_model = "claude-3-5-haiku-20241022"

    def __init__(self) -> None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise LLMProviderError(
                "Anthropic provider not configured (missing ANTHROPIC_API_KEY)."
            )
        self._client = anthropic.Anthropic(api_key=api_key)

    @staticmethod
    def _split_system(messages: List[LLMMessage]) -> tuple[str, list[dict]]:
        """Anthropic takes `system` as a separate top-level param."""
        system_parts = [m.content for m in messages if m.role == "system"]
        turns = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role != "system"
        ]
        return "\n\n".join(system_parts), turns

    @staticmethod
    def _usage(resp) -> Optional[dict]:
        usage = getattr(resp, "usage", None)
        if usage is None:
            return None
        return {
            "prompt_tokens": getattr(usage, "input_tokens", None),
            "completion_tokens": getattr(usage, "output_tokens", None),
        }

    def chat(
        self,
        messages: List[LLMMessage],
        *,
        model: Optional[str] = None,
        temperature: float = 0.3,
    ) -> LLMResult:
        model = model or self.default_model
        system, turns = self._split_system(messages)
        try:
            resp = self._client.messages.create(
                model=model,
                max_tokens=_MAX_TOKENS,
                temperature=temperature,
                system=system or anthropic.NOT_GIVEN,
                messages=turns,
            )
        except Exception as e:
            raise LLMProviderError(f"Anthropic chat error: {e}") from e
        content = "".join(
            block.text for block in resp.content if getattr(block, "type", None) == "text"
        ).strip()
        return LLMResult(content=content, model=model, usage=self._usage(resp))

    def chat_json(
        self,
        messages: List[LLMMessage],
        *,
        model: Optional[str] = None,
        temperature: float = 0.3,
    ) -> LLMResult:
        # No native JSON mode — ask for it explicitly and let the caller
        # parse leniently with parse_json_loose().
        return self.chat(with_json_instruction(messages), model=model, temperature=temperature)
