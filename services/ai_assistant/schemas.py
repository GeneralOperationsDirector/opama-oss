"""
AI Assistant — request/response schemas.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


# --- Personal access tokens -------------------------------------------------

class ApiTokenCreate(BaseModel):
    name: str


class ApiTokenOut(BaseModel):
    id: int
    name: str
    hint: str
    created_at: datetime
    last_used_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None


class ApiTokenCreated(ApiTokenOut):
    token: str  # raw token — returned once, never again


# --- Chat ---------------------------------------------------------------------

class ChatMessageIn(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessageIn]
    model: Optional[str] = None
    temperature: Optional[float] = 0.3


class PendingAction(BaseModel):
    id: str
    tool_name: str
    arguments: dict[str, Any]
    description: str


class ChatResponse(BaseModel):
    reply: str
    usage: Optional[dict[str, Any]] = None
    pending_action: Optional[PendingAction] = None


class ConfirmActionRequest(BaseModel):
    pending_action_id: str
    approve: bool


class ConfirmActionResponse(BaseModel):
    result: Optional[Any] = None
    message: str
