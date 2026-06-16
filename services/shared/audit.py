"""
Audit logging — append-only record of privileged actions.

Usage:
    from services.shared.audit import write_audit_log

    write_audit_log(
        session,
        action="plugin.install",
        user=current_user,
        target=plugin_id,
        request=request,
        detail="installed from https://...",
    )

Writing an audit row is a side effect of the action, never the point of it —
failures here must not break the calling endpoint, so every error is caught
and logged rather than raised.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import Request
from slowapi.util import get_remote_address
from sqlmodel import Session

from services.shared.models import User
from services.shared.models_security import AuditLog

log = logging.getLogger(__name__)


def write_audit_log(
    session: Session,
    *,
    action: str,
    user: Optional[User] = None,
    target: Optional[str] = None,
    request: Optional[Request] = None,
    success: bool = True,
    detail: Optional[str] = None,
) -> None:
    """Append an AuditLog row for a privileged action. Never raises."""
    try:
        entry = AuditLog(
            user_id=user.id if user else None,
            action=action,
            target=target,
            ip_address=get_remote_address(request) if request else None,
            success=success,
            detail=detail,
        )
        session.add(entry)
        session.commit()
    except Exception:
        session.rollback()
        log.warning("Failed to write audit log entry for action=%s", action, exc_info=True)
