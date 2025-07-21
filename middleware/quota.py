"""Token quota middleware for Attach Gateway.

Enforces per-user token limits using a sliding 1-minute window. The
quota is applied to both the request body and the response body.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from collections import deque
from typing import Deque, Dict, Optional, Protocol, Tuple
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, StreamingResponse

from usage.backends import NullUsageBackend

logger = logging.getLogger(__name__)


class AbstractMeterStore(Protocol):
    """Interface for token accounting backends."""

    async def increment(self, user: str, tokens: int) -> Tuple[int, float]:
        """Return the running total and timestamp of the oldest entry."""


class InMemoryMeterStore:
    """Simple in-memory sliding window counter.

    Not safe for multi-process deployments; each process keeps its own
    counters. Use :class:`RedisMeterStore` in production.
    """

    def __init__(self, window: int = 60) -> None:
        self.window = window
        self._data: Dict[str, Deque[Tuple[float, int]]] = {}

    async def increment(self, user: str, tokens: int) -> Tuple[int, float]:
        now = time.time()
        dq = self._data.setdefault(user, deque())
        dq.append((now, tokens))
        cutoff = now - self.window
        while dq and dq[0][0] < cutoff:
            dq.popleft()
        total = sum(t for _, t in dq)
        oldest = dq[0][0] if dq else now
        return total, oldest


class RedisMeterStore:
    """Redis backed sliding window counter."""

    def __init__(self, url: str = "redis://localhost:6379", window: int = 60) -> None:
        import redis.asyncio as redis  # type: ignore

        self.window = window
        self.redis = redis.from_url(url, decode_responses=True)

    async def increment(self, user: str, tokens: int) -> Tuple[int, float]:
        now = time.time()
        key = f"attach:quota:{user}"
        member = f"{now}:{tokens}"
        async with self.redis.pipeline(transaction=True) as pipe:
            await pipe.zadd(key, {member: now})
            await pipe.zremrangebyscore(key, 0, now - self.window)
            await pipe.zrange(key, 0, -1, withscores=True)
            results = await pipe.execute()
        entries = results[-1]
        total = 0
        oldest = now
        for member, ts in entries:
            try:
                _, tok = member.split(":", 1)
                total += int(tok)
            except Exception:
                pass
            oldest = min(oldest, ts)
        return total, oldest


class TokenQuotaMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware enforcing per-user token quotas."""

    def __init__(self, app, store: Optional[AbstractMeterStore] = None) -> None:
        """Create middleware.

        Must be added **after** :func:`session_mw` so the ``X-Attach-User``
        header or client IP is available for quota tracking.
        """
        super().__init__(app)
        self.store = store or InMemoryMeterStore()
        self.window = 60
        self.max_tokens = int(os.getenv("MAX_TOKENS_PER_MIN", "60000"))
        enc_name = os.getenv("QUOTA_ENCODING", "cl100k_base")
        try:
            import tiktoken

            self.encoder = tiktoken.get_encoding(enc_name)
        except Exception:  # pragma: no cover - fallback
            if "tiktoken" not in sys.modules:
                logger.warning(
                    "tiktoken missing – using byte-count fallback; token metrics may be inflated"
                )

            class _Simple:
                def encode(self, text: str) -> list[int]:
                    return list(text.encode())

            self.encoder = _Simple()

    @staticmethod
    def _is_textual(mime: str) -> bool:
        return mime.startswith("text/") or "json" in mime

    def _num_tokens(self, text: str) -> int:
        return len(self.encoder.encode(text))

    @staticmethod
    def _is_monitoring_endpoint(path: str) -> bool:
        """Monitoring endpoints that should skip token-based rate limiting."""
        monitoring_paths = [
            "/metrics",      # Prometheus metrics
            "/mem/events",   # Memory events
            "/auth/config",  # Auth configuration
        ]
        return any(path.startswith(p) for p in monitoring_paths)

    async def dispatch(self, request: Request, call_next):
        # Skip token-based rate limiting for monitoring endpoints
        if self._is_monitoring_endpoint(request.url.path):
            return await call_next(request)
            
        if not hasattr(request.app.state, "usage"):
            request.app.state.usage = NullUsageBackend()
        user = request.headers.get("x-attach-user")
        if not user:
            user = request.client.host if request.client else "unknown"
        usage = {
            "user": user,
            "project": request.headers.get("x-attach-project", "default"),
            "tokens_in": 0,
            "tokens_out": 0,
            "model": "unknown",
            "request_id": request.headers.get("x-request-id") or str(uuid4()),
        }

        body = await request.body()
        content_type = request.headers.get("content-type", "")
        tokens = 0
        if self._is_textual(content_type):
            tokens = self._num_tokens(body.decode("utf-8", "ignore"))
        usage["tokens_in"] = tokens
        total, oldest = await self.store.increment(user, tokens)
        request.state._usage = usage
        if total > self.max_tokens:
            retry_after = max(0, int(self.window - (time.time() - oldest)))
            usage["ts"] = time.time()
            await request.app.state.usage.record(**usage)
            return JSONResponse(
                {"detail": "token quota exceeded", "retry_after": retry_after},
                status_code=429,
            )

        response = await call_next(request)
        usage["model"] = response.headers.get("x-llm-model", "unknown")

        first_chunk = None
        try:
            first_chunk = await response.body_iterator.__anext__()
        except StopAsyncIteration:
            pass

        media = response.media_type or response.headers.get("content-type", "")
        if first_chunk is not None and self._is_textual(media):
            tokens_chunk = self._num_tokens(first_chunk.decode("utf-8", "ignore"))
            total, oldest = await self.store.increment(user, tokens_chunk)
            if total > self.max_tokens:
                retry_after = max(0, int(self.window - (time.time() - oldest)))
                usage["tokens_out"] += tokens_chunk
                usage["ts"] = time.time()
                await request.app.state.usage.record(**usage)
                return JSONResponse(
                    {"detail": "token quota exceeded", "retry_after": retry_after},
                    status_code=429,
                )
            usage["tokens_out"] += tokens_chunk

        async def stream_with_quota():
            nonlocal total, oldest
            if first_chunk is not None:
                yield first_chunk
            async for chunk in response.body_iterator:
                tokens_chunk = 0
                media = response.media_type or response.headers.get("content-type", "")
                if self._is_textual(media):
                    tokens_chunk = self._num_tokens(chunk.decode("utf-8", "ignore"))
                next_total, oldest = await self.store.increment(user, tokens_chunk)
                if next_total > self.max_tokens:
                    break
                total = next_total
                if tokens_chunk:
                    usage["tokens_out"] += tokens_chunk
                yield chunk

            usage["ts"] = time.time()
            await request.app.state.usage.record(**usage)

        return StreamingResponse(
            stream_with_quota(),
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )
