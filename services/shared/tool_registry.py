"""
Shared AI tool registry.

Any module can contribute tools the AI Assistant (and MCP clients connected
via a personal access token) can call: declare a `TOOLS: list[ToolDefinition]`
in a `tools.py` module and point `tools_module:` at it in `plugin.yaml`.
`app/plugin_loader.py` imports that module and calls `register_tools()` —
this registry is the only thing both `ai_assistant` and every
tool-contributing module need to import, so no module depends on
`ai_assistant` and vice versa.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from fastapi.encoders import jsonable_encoder
from sqlmodel import Session

from services.shared.llm import ToolSpec
from services.shared.models import User

logger = logging.getLogger(__name__)


@dataclass
class ToolDefinition:
    spec: ToolSpec
    handler: Callable[[Session, User, dict], Any]
    mutating: bool


_REGISTRY: Dict[str, ToolDefinition] = {}


def register_tools(tools: List[ToolDefinition]) -> None:
    for tool in tools:
        if tool.spec.name in _REGISTRY:
            logger.warning("Tool %r registered more than once — overwriting", tool.spec.name)
        _REGISTRY[tool.spec.name] = tool


def get_tool(name: str) -> Optional[ToolDefinition]:
    return _REGISTRY.get(name)


def list_tool_specs(include_mutating: bool = True) -> List[ToolSpec]:
    return [
        tool.spec for tool in _REGISTRY.values()
        if include_mutating or not tool.mutating
    ]


def execute_tool(name: str, session: Session, user: User, arguments: dict) -> dict:
    """Runs the tool handler and returns a JSON-safe dict. Never raises —
    handler errors are caught and returned as `{"error": str(e)}` so a bad
    tool call can't break the chat loop or an MCP response."""
    tool = get_tool(name)
    if tool is None:
        return {"error": f"Unknown tool: {name!r}"}
    try:
        result = tool.handler(session, user, arguments or {})
        return jsonable_encoder(result)
    except Exception as e:
        logger.exception("Tool %r failed", name)
        return {"error": str(e)}
