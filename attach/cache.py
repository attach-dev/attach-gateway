from __future__ import annotations

"""Simple runtime-swappable cache implementations."""

import hashlib
import json
from typing import Any, Optional

import redis


class _MemoryCache:
    """In-memory dictionary cache."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def get(self, key: str) -> Any | None:
        return self._data.get(key)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value


class _RedisCache:
    """Redis-backed cache."""

    def __init__(self, url: str) -> None:
        self._client = redis.Redis.from_url(url)

    def get(self, key: str) -> Any | None:
        val = self._client.get(key)
        if val is None:
            return None
        try:
            return json.loads(val)
        except Exception:
            return None

    def set(self, key: str, value: Any) -> None:
        self._client.set(key, json.dumps(value))


def build_cache(kind: str = "memory", redis_url: Optional[str] = None) -> Any:
    """Return a cache instance for ``kind``."""

    kind = (kind or "memory").lower()
    if kind == "redis":
        url = redis_url or "redis://localhost:6379/0"
        return _RedisCache(url)
    return _MemoryCache()


def cache_key(model: str, messages: str, params: dict) -> str:
    """Compute a deterministic cache key."""

    blob = model + messages + json.dumps(params, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()
