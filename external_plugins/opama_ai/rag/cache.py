# app/ai/cache.py
"""
Redis-backed JSON cache for AI & suggestions.

- Stable, namespaced keys derived from a JSON payload (SHA1 digest).
- JSON values only (keeps payloads portable & inspectable).
- Graceful degradation: if Redis is unavailable, getters return None and setters no-op.

Env:
  REDIS_URL            redis://localhost:6379/0
  CACHE_NAMESPACE      ptcg:ai
  CACHE_VERSION        v1           # bump to invalidate all keys
  CACHE_TTL_SECONDS    86400        # default TTL

Public API (backwards compatible):
  get(payload: Mapping) -> Any | None
  set(payload: Mapping, value: Any, ttl: int = DEFAULT_TTL) -> bool
  delete(payload: Mapping) -> int
  exists(payload: Mapping) -> bool
  cached(ttl: int = DEFAULT_TTL, key_fn: Callable = None) -> decorator
  r  # redis client (for legacy access)
"""

from __future__ import annotations
import hashlib
import json
import os
import typing as t
import redis
from functools import wraps

# --- Config -----------------------------------------------------------------
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
KEY_NS = os.getenv("CACHE_NAMESPACE", "ptcg:ai")
CACHE_VERSION = os.getenv("CACHE_VERSION", "v1")
DEFAULT_TTL = int(os.getenv("CACHE_TTL_SECONDS", "86400"))

# --- Client (lazy) ----------------------------------------------------------
_redis_client: redis.Redis | None = None


def _client() -> redis.Redis:
    """
    Lazily create a Redis client. Binary-safe (decode_responses=False).
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=False)
    return _redis_client


# Back-compat export (some code may import and use `cache.r`)
r = _client()


# --- Keying -----------------------------------------------------------------
def _key(payload: t.Mapping[str, t.Any]) -> str:
    """
    Stable key from a JSON-serializable payload:
      ns:version:sha1(json.dumps(payload, sort_keys=True))
    """
    blob = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    digest = hashlib.sha1(blob.encode("utf-8")).hexdigest()
    return f"{KEY_NS}:{CACHE_VERSION}:{digest}"


# --- Primitives -------------------------------------------------------------
def get(payload: t.Mapping[str, t.Any]) -> t.Any | None:
    """
    Fetch a JSON value for `payload`. Returns None on miss or Redis error.
    """
    try:
        v = _client().get(_key(payload))
        return json.loads(v) if v else None  # json.loads accepts bytes
    except Exception:
        return None


def set(payload: t.Mapping[str, t.Any], value: t.Any, ttl: int = DEFAULT_TTL) -> bool:
    """
    Store a JSON value with TTL. Returns False if Redis write fails.
    """
    try:
        data = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        _client().setex(_key(payload), int(ttl), data.encode("utf-8"))
        return True
    except Exception:
        return False


def delete(payload: t.Mapping[str, t.Any]) -> int:
    """Delete a cached entry. Returns number of keys removed (0/1)."""
    try:
        return int(_client().delete(_key(payload)) or 0)
    except Exception:
        return 0


def exists(payload: t.Mapping[str, t.Any]) -> bool:
    """True if a cache entry currently exists (best-effort)."""
    try:
        return bool(_client().exists(_key(payload)))
    except Exception:
        return False


# --- Decorator --------------------------------------------------------------
def cached(
    ttl: int = DEFAULT_TTL, key_fn: t.Callable[..., t.Mapping[str, t.Any]] | None = None
):
    """
    Decorate a function to cache its return value in Redis.

    Example:
        @cached(ttl=3600, key_fn=lambda deck_id: {"route":"suggest","deck_id":deck_id})
        def compute(deck_id: int) -> dict:
            ...

    If `key_fn` is omitted, args/kwargs are used directly (must be JSON-serializable).
    """

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            payload = (
                key_fn(*args, **kwargs)
                if key_fn
                else {"fn": fn.__name__, "args": args, "kwargs": kwargs}
            )
            hit = get(payload)
            if hit is not None:
                return hit
            result = fn(*args, **kwargs)
            set(payload, result, ttl=ttl)
            return result

        return wrapper

    return decorator
