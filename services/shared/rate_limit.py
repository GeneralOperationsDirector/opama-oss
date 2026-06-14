"""
Rate limiting utilities for API endpoints.

This module provides a simple rate limiting decorator that can be applied to FastAPI endpoints.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# Create global limiter instance
limiter = Limiter(key_func=get_remote_address)


def rate_limit(limit_string: str):
    """
    Decorator to apply rate limiting to FastAPI endpoints.

    Usage:
        @router.post("/expensive-endpoint")
        @rate_limit("10/minute")
        async def my_endpoint(request: Request):
            ...

    Args:
        limit_string: Rate limit in format "number/period" (e.g., "10/minute", "100/hour")
                     Valid periods: second, minute, hour, day
    """
    def decorator(func):
        # Add the limiter decorator
        return limiter.limit(limit_string)(func)

    return decorator
