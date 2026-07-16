"""
Unit tests for the LLM provider abstraction (external_plugins/opama_ai/providers/).

Pure-logic tests with mocked SDK clients — no live API calls to OpenAI,
Anthropic, or Ollama.

Run with:
    pytest tests/test_ai_providers.py -v
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("openai")
pytest.importorskip("anthropic")

from services.shared.llm import (
    LLMMessage,
    LLMProviderError,
    get_provider,
    parse_json_loose,
    with_json_instruction,
)
from services.shared.llm.anthropic_provider import AnthropicProvider
from services.shared.llm.ollama_provider import OllamaProvider
from services.shared.llm.openai_provider import OpenAIProvider


# ---------------------------------------------------------------------------
# parse_json_loose
# ---------------------------------------------------------------------------


def test_parse_json_loose_clean():
    assert parse_json_loose('{"a": 1}') == {"a": 1}


def test_parse_json_loose_with_prose():
    content = 'Sure, here you go:\n```json\n{"a": 1, "b": [2, 3]}\n```\nHope that helps!'
    assert parse_json_loose(content) == {"a": 1, "b": [2, 3]}


def test_parse_json_loose_invalid():
    with pytest.raises(json.JSONDecodeError):
        parse_json_loose("not json at all")


# ---------------------------------------------------------------------------
# with_json_instruction
# ---------------------------------------------------------------------------


def test_with_json_instruction_merges_into_leading_system_message():
    messages = [
        LLMMessage(role="system", content="Be concise."),
        LLMMessage(role="user", content="hi"),
    ]
    out = with_json_instruction(messages)

    assert len(out) == 2
    assert out[0].role == "system"
    assert "Be concise." in out[0].content
    assert "JSON" in out[0].content
    assert out[1] == messages[1]


def test_with_json_instruction_inserts_leading_system_message_when_absent():
    messages = [LLMMessage(role="user", content="hi")]
    out = with_json_instruction(messages)

    assert len(out) == 2
    assert out[0].role == "system"
    assert "JSON" in out[0].content
    assert out[1] == messages[0]


# ---------------------------------------------------------------------------
# get_provider() resolution
# ---------------------------------------------------------------------------


def test_get_provider_defaults_to_openai(monkeypatch):
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    provider = get_provider()
    assert isinstance(provider, OpenAIProvider)


def test_get_provider_explicit_override(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    provider = get_provider("anthropic")
    assert isinstance(provider, AnthropicProvider)


def test_get_provider_unknown_raises(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "watson")
    with pytest.raises(LLMProviderError):
        get_provider()


def test_openai_provider_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPEN_API_KEY", raising=False)
    with pytest.raises(LLMProviderError):
        OpenAIProvider()


def test_anthropic_provider_requires_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMProviderError):
        AnthropicProvider()


def test_ollama_provider_never_requires_config(monkeypatch):
    monkeypatch.delenv("OLLAMA_URL", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    provider = OllamaProvider()
    assert provider.default_model == "llama3.2"


# ---------------------------------------------------------------------------
# OpenAIProvider.chat / chat_json
# ---------------------------------------------------------------------------


def _openai_response(content: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(model_dump=lambda: {"total_tokens": 42}),
    )


def test_openai_chat(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    provider = OpenAIProvider()
    provider._client = MagicMock()
    provider._client.chat.completions.create.return_value = _openai_response("hello!")

    result = provider.chat([LLMMessage(role="user", content="hi")])

    assert result.content == "hello!"
    assert result.model == "gpt-4o-mini"
    assert result.usage == {"total_tokens": 42}


def test_openai_chat_json_sets_response_format(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    provider = OpenAIProvider()
    provider._client = MagicMock()
    provider._client.chat.completions.create.return_value = _openai_response('{"x": 1}')

    result = provider.chat_json([LLMMessage(role="user", content="give me json")], model="gpt-4o")

    kwargs = provider._client.chat.completions.create.call_args.kwargs
    assert kwargs["response_format"] == {"type": "json_object"}
    assert parse_json_loose(result.content) == {"x": 1}


def test_openai_chat_upstream_error_raises_provider_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    provider = OpenAIProvider()
    provider._client = MagicMock()
    provider._client.chat.completions.create.side_effect = RuntimeError("boom")

    with pytest.raises(LLMProviderError):
        provider.chat([LLMMessage(role="user", content="hi")])


# ---------------------------------------------------------------------------
# AnthropicProvider.chat / chat_json
# ---------------------------------------------------------------------------


def _anthropic_response(text: str):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )


def test_anthropic_chat_splits_system_message(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    provider = AnthropicProvider()
    provider._client = MagicMock()
    provider._client.messages.create.return_value = _anthropic_response("hi there")

    result = provider.chat(
        [
            LLMMessage(role="system", content="You are helpful."),
            LLMMessage(role="user", content="hello"),
        ]
    )

    kwargs = provider._client.messages.create.call_args.kwargs
    assert kwargs["system"] == "You are helpful."
    assert kwargs["messages"] == [{"role": "user", "content": "hello"}]
    assert result.content == "hi there"
    assert result.usage == {"prompt_tokens": 10, "completion_tokens": 5}


def test_anthropic_chat_json_appends_instruction(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    provider = AnthropicProvider()
    provider._client = MagicMock()
    provider._client.messages.create.return_value = _anthropic_response('{"ok": true}')

    result = provider.chat_json([LLMMessage(role="user", content="give me json")])

    kwargs = provider._client.messages.create.call_args.kwargs
    assert "JSON" in kwargs["system"]
    assert parse_json_loose(result.content) == {"ok": True}


# ---------------------------------------------------------------------------
# OllamaProvider.chat / chat_json
# ---------------------------------------------------------------------------


def test_ollama_chat_uses_configured_default_model(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.1")
    provider = OllamaProvider()
    provider._client = MagicMock()
    provider._client.chat.completions.create.return_value = _openai_response("hi")

    result = provider.chat([LLMMessage(role="user", content="hello")])

    assert result.model == "llama3.1"
    kwargs = provider._client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "llama3.1"


def test_ollama_chat_json_appends_instruction(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.1")
    provider = OllamaProvider()
    provider._client = MagicMock()
    provider._client.chat.completions.create.return_value = _openai_response('{"ok": true}')

    provider.chat_json([LLMMessage(role="user", content="give me json")])

    kwargs = provider._client.chat.completions.create.call_args.kwargs
    messages = kwargs["messages"]
    assert any("JSON" in m["content"] for m in messages if m["role"] == "system")
