"""
Security models — UserSecret vault and AuditLog.

UserSecret: per-user encrypted storage for third-party API keys and tokens.
AuditLog:   append-only record of privileged actions (plugin installs,
            secret changes, publish events, settings changes).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class UserSecret(SQLModel, table=True):
    """
    Encrypted per-user secret storage.

    One row per (user_id, service) pair. The service name is a short slug
    identifying the external system, e.g. "github_pat", "openai_api_key".

    encrypted_value is the output of app.secrets.encrypt_secret() — an
    AES-256-GCM ciphertext encoded as base64url. It is NEVER returned to
    the client; only the hint (last 4 chars) is exposed.
    """

    __tablename__ = "user_secret"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    service: str = Field(index=True)        # e.g. "github_pat", "openai_api_key"
    encrypted_value: str                    # AES-256-GCM via app.secrets
    hint: Optional[str] = None             # last 4 chars, e.g. "…a4f2"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_used_at: Optional[datetime] = None


class AuditLog(SQLModel, table=True):
    """
    Append-only audit trail for privileged actions.

    Written on:
      - plugin install / uninstall
      - secret set / delete
      - storefront publish
      - storefront settings change
      - admin role changes (future)

    Never modified after insert. Accessible via GET /system/audit (admin only).
    """

    __tablename__ = "audit_log"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = None          # None for system-initiated actions
    action: str                            # dot-namespaced, e.g. "plugin.install"
    target: Optional[str] = None           # plugin_id, service name, etc.
    ip_address: Optional[str] = None
    success: bool = True
    detail: Optional[str] = None           # short human-readable description
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
