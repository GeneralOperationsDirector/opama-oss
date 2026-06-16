"""
AI Assistant — SQLModel tables.

ApiToken is the only table this module owns, but it's a credential table
(alongside UserSecret/AuditLog), so it's defined in
services/shared/models_security.py and re-exported here for
model_modules discovery / documentation. It's already registered with
SQLModel's metadata via app/main.py's unconditional models_security import.
"""

from services.shared.models_security import ApiToken  # noqa: F401
