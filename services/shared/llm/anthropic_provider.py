import os
from typing import List, Optional

import anthropic

from .base import LLMMessage, LLMProvider, LLMProviderError, LLMResult, ToolCall, ToolSpec, with_json_instruction

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
    def _to_anthropic_messages(messages: List[LLMMessage]) -> tuple[str, list[dict]]:
        """Anthropic takes `system` as a separate top-level param, and
        represents tool calls/results as content blocks within
        assistant/user turns rather than dedicated roles. Consecutive
        `tool` messages (multiple results for one assistant turn) are
        merged into a single user message — Anthropic expects all
        `tool_result` blocks for a turn together."""
        system_parts: list[str] = []
        turns: list[dict] = []
        for m in messages:
            if m.role == "system":
                system_parts.append(m.content)
            elif m.role == "tool":
                block = {"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content}
                if turns and turns[-1]["role"] == "user" and isinstance(turns[-1]["content"], list) \
                        and turns[-1]["content"] and turns[-1]["content"][0].get("type") == "tool_result":
                    turns[-1]["content"].append(block)
                else:
                    turns.append({"role": "user", "content": [block]})
            elif m.tool_calls:
                content: list[dict] = []
                if m.content:
                    content.append({"type": "text", "text": m.content})
                for tc in m.tool_calls:
                    content.append({"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments})
                turns.append({"role": "assistant", "content": content})
            else:
                turns.append({"role": m.role, "content": m.content})
        return "\n\n".join(system_parts), turns

    @staticmethod
    def _to_anthropic_tools(tools: Optional[List[ToolSpec]]) -> Optional[List[dict]]:
        if not tools:
            return None
        return [{"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools]

    @staticmethod
    def _extract_tool_calls(resp) -> List[ToolCall]:
        calls = []
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                calls.append(ToolCall(id=block.id, name=block.name, arguments=block.input or {}))
        return calls

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
        tools: Optional[List[ToolSpec]] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResult:
        model = model or self.default_model
        system, turns = self._to_anthropic_messages(messages)
        kwargs = {}
        anthropic_tools = self._to_anthropic_tools(tools)
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools
        try:
            resp = self._client.messages.create(
                model=model,
                max_tokens=max_tokens or _MAX_TOKENS,
                temperature=temperature,
                system=system or anthropic.NOT_GIVEN,
                messages=turns,
                **kwargs,
            )
        except Exception as e:
            raise LLMProviderError(f"Anthropic chat error: {e}") from e
        content = "".join(
            block.text for block in resp.content if getattr(block, "type", None) == "text"
        ).strip()
        return LLMResult(content=content, model=model, usage=self._usage(resp), tool_calls=self._extract_tool_calls(resp))

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
