import json
import os
from typing import List, Optional

from openai import OpenAI

from .base import LLMMessage, LLMProvider, LLMProviderError, LLMResult, ToolCall, ToolSpec


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

    @staticmethod
    def _to_openai_messages(messages: List[LLMMessage]) -> List[dict]:
        out = []
        for m in messages:
            if m.role == "tool":
                out.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content})
            elif m.tool_calls:
                out.append({
                    "role": "assistant",
                    "content": m.content or None,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                        }
                        for tc in m.tool_calls
                    ],
                })
            else:
                out.append({"role": m.role, "content": m.content})
        return out

    @staticmethod
    def _to_openai_tools(tools: Optional[List[ToolSpec]]) -> Optional[List[dict]]:
        if not tools:
            return None
        return [
            {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
            for t in tools
        ]

    @staticmethod
    def _tool_calls(message) -> List[ToolCall]:
        raw = getattr(message, "tool_calls", None) or []
        calls = []
        for tc in raw:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except (json.JSONDecodeError, TypeError):
                args = {}
            calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        return calls

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
        kwargs = {}
        openai_tools = self._to_openai_tools(tools)
        if openai_tools:
            kwargs["tools"] = openai_tools
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        try:
            resp = self._client.chat.completions.create(
                model=model,
                temperature=temperature,
                messages=self._to_openai_messages(messages),
                **kwargs,
            )
        except Exception as e:
            raise LLMProviderError(f"OpenAI chat error: {e}") from e
        message = resp.choices[0].message
        return LLMResult(
            content=(message.content or "").strip(),
            model=model,
            usage=self._usage(resp),
            tool_calls=self._tool_calls(message),
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
