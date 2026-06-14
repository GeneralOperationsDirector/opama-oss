"""
Combined AI router.

Aggregates suggest_router (registered at /suggest) and chat_router
(self-prefixed at /ai) into a single plugin entry point.
"""
from fastapi import APIRouter
from .suggest_router import router as suggest_router
from .chat_router import router as chat_router

router = APIRouter()
router.include_router(suggest_router, prefix="/suggest", tags=["suggest"])
router.include_router(chat_router)
