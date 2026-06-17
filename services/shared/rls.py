"""Postgres Row-Level Security (RLS) plumbing for the pool tenancy model.

RLS is the safety net *behind* the app-layer org scoping (see the pool_vs_silo
design memory): even if a query forgets `WHERE org_id = …`, Postgres policies on
every org-scoped table restrict rows to the request's *active org*. The active org
is carried in a transaction-local GUC, `app.current_org_id`, set per request.

Enforcement requires the app to connect as a **non-superuser, non-owner** role —
superusers and table owners bypass RLS. The `opama_app` role + policies are created
by the `b6c7d8e9f0a1` migration; production points DATABASE_URL at that role. While
the app connects as a superuser (the current dev default) RLS is bypassed and these
GUC writes are harmless no-ops, so this module is safe to ship *ahead* of the
connection-role flip.

Why a transaction listener: `set_config(…, is_local => true)` (≡ `SET LOCAL`) is
scoped to the current transaction. Handlers commit mid-request, and the next
transaction would otherwise lose the GUC — and a missing GUC fails *closed* to zero
rows (`current_setting('app.current_org_id', true)` → NULL). So the GUC must be
re-applied at the start of every transaction on a stamped session. `after_begin`
does that; `stamp_session_org` records the org on the session and also applies it to
the already-open transaction (the one org resolution itself opened).
"""
from __future__ import annotations

from sqlalchemy import event, text
from sqlmodel import Session

# Custom GUC carrying the active org for the connection's current transaction.
ORG_GUC = "app.current_org_id"
_SET_GUC = text(f"SELECT set_config('{ORG_GUC}', :org_id, true)")


def stamp_session_org(session: Session, org_id: int) -> None:
    """Bind `session` to `org_id` for RLS.

    Records the org on `session.info` so every *future* transaction on this session
    re-applies the GUC (via the `after_begin` listener), and applies it immediately
    to the transaction org resolution already opened. No-op on non-Postgres binds.
    """
    session.info["org_id"] = org_id
    if session.get_bind().dialect.name == "postgresql":
        session.execute(_SET_GUC, {"org_id": str(org_id)})


@event.listens_for(Session, "after_begin")
def _reapply_org_guc(session, transaction, connection) -> None:
    """Re-apply the active-org GUC at the start of each transaction on a stamped
    session (covers the fresh transaction that begins after a mid-request commit)."""
    org_id = session.info.get("org_id")
    if org_id is not None and connection.dialect.name == "postgresql":
        connection.execute(_SET_GUC, {"org_id": str(org_id)})
