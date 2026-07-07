from __future__ import annotations

import os
import threading

_lock = threading.Lock()
_client = None


def redis_url() -> str:
    return os.environ.get("REDIS_URL", "").strip()


def redis_enabled() -> bool:
    return bool(redis_url())


def get_redis():
    global _client
    if not redis_enabled():
        raise RuntimeError("REDIS_URL is not configured")
    with _lock:
        if _client is None:
            import redis

            _client = redis.from_url(redis_url(), decode_responses=True)
        return _client


def ping_redis() -> bool:
    if not redis_enabled():
        return False
    try:
        return bool(get_redis().ping())
    except Exception:
        return False


def reset_redis_client() -> None:
    global _client
    with _lock:
        _client = None
