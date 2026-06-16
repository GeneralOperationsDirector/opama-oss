"""
Authentication service.

Handles Firebase authentication and user management.
"""

from .firebase_admin import init_firebase_admin, verify_id_token, get_user_by_uid
from .middleware import get_current_user, get_optional_user
from .router import router

__all__ = [
    "init_firebase_admin",
    "verify_id_token",
    "get_user_by_uid",
    "get_current_user",
    "get_optional_user",
    "router",
]
