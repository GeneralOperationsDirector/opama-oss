"""
AI Assistant — router.

Three groups of endpoints:

1. **Personal access tokens** (`/ai-assistant/tokens`) — browser-session
   auth (get_current_user). Generate/list/revoke `opat_...` tokens that
   external agents use to call the MCP endpoint below.

2. **Chat** (`/ai-assistant/chat`, `/ai-assistant/chat/confirm`) — browser-
   session auth. A tool-calling chat loop over whatever tools every module
   registered via services.shared.tool_registry (custom_assets, vehicles,
   insurance, real_estate, ...). Read-only tools run immediately; mutating
   tools are held as a "pending action" until the user confirms.

3. **MCP — Streamable HTTP** (`/ai-assistant/mcp`) — PAT-bearer auth
   (get_user_from_pat). Lets external agents (e.g. Claude Code via
   `claude mcp add --transport http`) list and call the same tools directly.

   TRUST BOUNDARY: a personal access token grants the bearer the SAME
   permissions as the user it belongs to, INCLUDING MUTATING TOOLS, with NO
   per-call confirmation step — calling `tools/call` on a mutating tool runs
   it immediately. This is analogous to handing an agent shell access to
   your account. Treat PATs like passwords: name them, revoke them when an
   agent no longer needs access, and never share one.
"""
from __future__ import annotations

import json
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlmodel import Session, select

from app.secrets import secret_hint, token_digest
from services.auth.middleware import get_current_user
from services.auth.pat import get_user_from_pat
from services.shared.audit import write_audit_log
from services.shared.database import get_session
from services.shared.llm import LLMMessage, LLMProviderError, get_provider
from services.shared.models import User
from services.shared.models_security import ApiToken
from services.shared.plugin_data import get_user_plugin_data, set_user_plugin_data
from services.shared.tool_registry import execute_tool, get_tool, list_tool_specs

from .schemas import (
    ApiTokenCreate,
    ApiTokenCreated,
    ApiTokenOut,
    ChatRequest,
    ChatResponse,
    ConfirmActionRequest,
    ConfirmActionResponse,
    PendingAction,
)

router = APIRouter(tags=["ai_assistant"])

PLUGIN_ID = "ai_assistant"
MODULE_VERSION = "0.1.0"
MCP_PROTOCOL_VERSION = "2025-03-26"
MAX_CHAT_ITERATIONS = 5

SYSTEM_PROMPT = (
    "You are opama's AI Assistant. You have read access to the user's data "
    "across every module they have enabled — Collections, Vehicle "
    "Maintenance, Insurance & Appraisals, Property Records, and more — via "
    "the tools available to you. Use tools to answer questions instead of "
    "guessing; never fabricate values. If a tool can create or modify data, "
    "call it anyway — the system will ask the user to confirm before it "
    "actually runs, so propose the action with the arguments you think are "
    "correct. Keep replies concise."
)


def _assert_owner(row: ApiToken, current_user: User) -> None:
    if row.user_id != current_user.id:
        raise HTTPException(403, "Not your access token")


def _describe_action(tool_name: str, arguments: dict) -> str:
    tool = get_tool(tool_name)
    base = tool.spec.description if tool else tool_name
    args_str = ", ".join(f"{k}={v!r}" for k, v in (arguments or {}).items())
    return f"{base} ({tool_name}: {args_str})" if args_str else f"{base} ({tool_name})"


# ---------------------------------------------------------------------------
# Personal access tokens
# ---------------------------------------------------------------------------

@router.post("/tokens", response_model=ApiTokenCreated, status_code=201)
def create_token(
    body: ApiTokenCreate,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    raw = f"opat_{secrets.token_urlsafe(24)}"
    row = ApiToken(
        user_id=current_user.id,
        name=body.name,
        token_hash=token_digest(raw),
        hint=f"opat_{secret_hint(raw)}",
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    # Build the response before write_audit_log()'s own commit expires `row`
    # (expired SQLModel instances serialize to {} via model_dump()).
    result = ApiTokenCreated(**row.model_dump(), token=raw)
    write_audit_log(session, action="ai_assistant.token.create", user=current_user, target=body.name, request=request)
    return result


@router.get("/tokens", response_model=list[ApiTokenOut])
def list_tokens(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    rows = session.exec(
        select(ApiToken).where(ApiToken.user_id == current_user.id).order_by(ApiToken.created_at.desc())
    ).all()
    return [ApiTokenOut(**r.model_dump()) for r in rows]


@router.delete("/tokens/{token_id}", status_code=204)
def revoke_token(
    token_id: int,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    row = session.get(ApiToken, token_id)
    if not row:
        raise HTTPException(404, f"Token {token_id} not found")
    _assert_owner(row, current_user)

    row.revoked_at = datetime.now(timezone.utc)
    session.add(row)
    session.commit()
    write_audit_log(session, action="ai_assistant.token.revoke", user=current_user, target=row.name, request=request)


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    provider = get_provider()
    tools = list_tool_specs()

    messages = [LLMMessage(role="system", content=SYSTEM_PROMPT)]
    messages += [LLMMessage(role=m.role, content=m.content) for m in body.messages]

    for _ in range(MAX_CHAT_ITERATIONS):
        try:
            result = provider.chat(
                messages,
                model=body.model,
                temperature=body.temperature if body.temperature is not None else 0.3,
                tools=tools,
                max_tokens=2048,
            )
        except LLMProviderError as e:
            raise HTTPException(502, str(e))

        if not result.tool_calls:
            return ChatResponse(reply=result.content, usage=result.usage)

        call = result.tool_calls[0]
        tool = get_tool(call.name)

        if tool is None:
            messages.append(LLMMessage(role="assistant", content=result.content, tool_calls=[call]))
            messages.append(LLMMessage(
                role="tool", content=json.dumps({"error": f"Unknown tool: {call.name}"}),
                tool_call_id=call.id, name=call.name,
            ))
            continue

        if tool.mutating:
            action_id = uuid.uuid4().hex[:12]
            data = get_user_plugin_data(session, PLUGIN_ID, current_user.id)
            pending = data.get("pending_actions", {})
            pending[action_id] = {"tool_name": call.name, "arguments": call.arguments}
            set_user_plugin_data(session, PLUGIN_ID, current_user.id, pending_actions=pending)
            description = _describe_action(call.name, call.arguments)
            return ChatResponse(
                reply=result.content or f"I'd like to {description}. Please confirm to proceed.",
                usage=result.usage,
                pending_action=PendingAction(
                    id=action_id, tool_name=call.name, arguments=call.arguments, description=description,
                ),
            )

        tool_result = execute_tool(call.name, session, current_user, call.arguments)
        messages.append(LLMMessage(role="assistant", content=result.content, tool_calls=[call]))
        messages.append(LLMMessage(role="tool", content=json.dumps(tool_result), tool_call_id=call.id, name=call.name))

    return ChatResponse(reply="I wasn't able to finish that in a reasonable number of steps — try rephrasing or breaking it into smaller questions.")


@router.post("/chat/confirm", response_model=ConfirmActionResponse)
def confirm_chat_action(
    body: ConfirmActionRequest,
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    data = get_user_plugin_data(session, PLUGIN_ID, current_user.id)
    pending = data.get("pending_actions", {})
    action = pending.pop(body.pending_action_id, None)
    set_user_plugin_data(session, PLUGIN_ID, current_user.id, pending_actions=pending)

    if action is None:
        raise HTTPException(404, "Pending action not found — it may have already been resolved")

    if not body.approve:
        return ConfirmActionResponse(message="Action cancelled.")

    result = execute_tool(action["tool_name"], session, current_user, action["arguments"])
    write_audit_log(
        session,
        action=f"ai_assistant.tool.{action['tool_name']}",
        user=current_user,
        target=str(action["arguments"]),
        request=request,
    )
    return ConfirmActionResponse(result=result, message=f"{action['tool_name']} completed.")


# ---------------------------------------------------------------------------
# MCP — Streamable HTTP (see module docstring for the trust boundary)
# ---------------------------------------------------------------------------

@router.get("/mcp")
def mcp_probe(current_user: User = Depends(get_user_from_pat)):
    """Some MCP clients probe with a plain GET before issuing JSON-RPC POSTs."""
    return {"status": "ok", "transport": "streamable-http"}


@router.post("/mcp")
async def mcp_endpoint(
    request: Request,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_user_from_pat),
):
    body = await request.json()
    method = body.get("method")
    msg_id = body.get("id")

    if method == "notifications/initialized":
        return Response(status_code=202)

    if method == "initialize":
        result = {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "opama", "version": MODULE_VERSION},
        }
    elif method == "tools/list":
        result = {
            "tools": [
                {"name": spec.name, "description": spec.description, "inputSchema": spec.parameters}
                for spec in list_tool_specs()
            ]
        }
    elif method == "tools/call":
        params = body.get("params") or {}
        tool_name = params.get("name")
        arguments = params.get("arguments") or {}
        tool_result = execute_tool(tool_name, session, current_user, arguments)
        result = {
            "content": [{"type": "text", "text": json.dumps(tool_result)}],
            "isError": isinstance(tool_result, dict) and "error" in tool_result,
        }
    else:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": "Method not found"}}

    return {"jsonrpc": "2.0", "id": msg_id, "result": result}
