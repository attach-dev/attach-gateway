from __future__ import annotations

"""Token quota middleware enforcing a sliding window budget."""

import json
import logging
import os
import time
from collections import deque
from typing import (
    AsyncIterator,
    Awaitable,
    Callable,
    Deque,
    Dict,
    Iterable,
    Protocol,
    Tuple,
)
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, StreamingResponse

# ─────────────────────────────────────────────────────────
# Tokenizer setup
# ─────────────────────────────────────────────────────────
try:
    import tiktoken  # type: ignore
except Exception:  # pragma: no cover
    tiktoken = None

# ≈ cl100k_base: ~4 bytes / token for typical English
_APPROX_BYTES_PER_TOKEN = 4

from usage.backends import NullUsageBackend
from utils.env import int_env

logger = logging.getLogger(__name__)


class AbstractMeterStore(Protocol):
    """Token accounting backend."""

    async def increment(self, user: str, tokens: int) -> Tuple[int, float]:
        """Increment ``user``'s counter and return ``(total, oldest_ts)``."""

    async def adjust(self, user: str, delta: int) -> Tuple[int, float]:
        """Atomically adjust ``user``'s total by ``delta``."""

    async def peek_total(self, user: str) -> int:
        """Return ``user``'s current total without mutating state."""


class InMemoryMeterStore:
    """Simple in-memory meter for tests and development."""

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

    async def adjust(self, user: str, delta: int) -> Tuple[int, float]:
        return await self.increment(user, delta)

    async def peek_total(self, user: str) -> int:
        total, _ = await self.increment(user, 0)
        dq = self._data.get(user)
        if total and dq:
            dq.pop()
        return total


class RedisMeterStore:
    """Redis backed sliding window meter."""

    def __init__(self, url: str, window: int = 60) -> None:
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
        for m, ts in entries:
            try:
                _, tok = m.split(":", 1)
                total += int(tok)
            except Exception:
                pass
            oldest = min(oldest, ts)
        return total, oldest

    async def adjust(self, user: str, delta: int) -> Tuple[int, float]:
        now = time.time()
        key = f"attach:quota:{user}"
        member = f"{now}:{delta}"
        async with self.redis.pipeline(transaction=True) as pipe:
            await pipe.zadd(key, {member: now})
            await pipe.zremrangebyscore(key, 0, now - self.window)
            await pipe.zrange(key, 0, -1, withscores=True)
            results = await pipe.execute()
        entries = results[-1]
        total = 0
        oldest = now
        for m, ts in entries:
            try:
                _, tok = m.split(":", 1)
                total += int(tok)
            except Exception:
                pass
            oldest = min(oldest, ts)
        return total, oldest

    async def peek_total(self, user: str) -> int:
        now = time.time()
        key = f"attach:quota:{user}"
        member = f"{now}:0:{uuid4().hex}"
        async with self.redis.pipeline(transaction=True) as pipe:
            await pipe.zadd(key, {member: now})
            await pipe.zremrangebyscore(key, 0, now - self.window)
            await pipe.zrange(key, 0, -1, withscores=True)
            pipe.zrem(key, member)
            results = await pipe.execute()
        entries = results[2]
        total = 0
        for m, _ in entries:
            try:
                _, tok = m.split(":", 1)
                total += int(tok)
            except Exception:
                pass
        return total


def _is_textual(mime: str) -> bool:
    mime = (mime or "").lower()
    if not mime or mime == "*/*":
        return False
    return mime.startswith("text/") or "json" in mime


# ---------------------------------------------------------------------------
# Token-count helpers
# ---------------------------------------------------------------------------

def _encoder_for_model(model: str):
    """Return a tiktoken encoder, falling back to byte count."""
    if tiktoken is None:  # fallback: 1 token ≈ 4 bytes

        class _Approx:
            def encode(self, text: str) -> list[int]:
                # Never return 0 → always count at least 1 token
                return [0] * max(1, len(text) // _APPROX_BYTES_PER_TOKEN)

        return _Approx()

    try:
        return tiktoken.encoding_for_model(model)
    except Exception:
        try:
            return tiktoken.get_encoding("cl100k_base")
        except Exception:

            class _Approx:
                def encode(self, text: str) -> list[int]:
                    return [0] * max(1, len(text) // _APPROX_BYTES_PER_TOKEN)

            return _Approx()


def _num_tokens(text: str, model: str = "cl100k_base") -> int:
    return len(_encoder_for_model(model).encode(text))


def num_tokens_from_messages(messages: Iterable[dict], model: str) -> int:
    enc = _encoder_for_model(model)
    total = 3
    for msg in messages:
        total += 4
        for k, v in msg.items():
            total += len(enc.encode(str(v)))
            if k == "name":
                total -= 1
    return total


async def async_iter(data: Iterable[bytes]) -> AsyncIterator[bytes]:
    for chunk in data:
        yield chunk


_SKIP_PATHS = {
    "/metrics",
    "/mem/events",
    "/auth/config",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
}


class TokenQuotaMiddleware(BaseHTTPMiddleware):
    """Apply per-user LLM token quotas."""

    def __init__(self, app, store: AbstractMeterStore | None = None) -> None:
        super().__init__(app)
        self.window = int(os.getenv("WINDOW", "60"))
        self.max_tokens: int | None = int_env("MAX_TOKENS_PER_MIN", 60000)
        if store is not None:
            self.store = store
        else:
            redis_url = os.getenv("REDIS_URL")
            self.store = (
                RedisMeterStore(redis_url, self.window)
                if redis_url
                else InMemoryMeterStore(self.window)
            )

    class _Streamer:
        def __init__(
            self,
            iterator: AsyncIterator[bytes],
            *,
            user: str,
            store: AbstractMeterStore,
            max_tokens: int | None,
            is_textual: bool,
        ) -> None:
            self.iterator = iterator
            self.tail = bytearray()
            self.on_complete: Callable[[], Awaitable[None]] | None = None
            self.user = user
            self.store = store
            self.limit = max_tokens
            self.is_textual = is_textual
            self.quota_exceeded = False

        def __aiter__(self) -> AsyncIterator[bytes]:
            return self._gen()

        async def _gen(self) -> AsyncIterator[bytes]:
            try:
                async for chunk in self.iterator:
                    self.tail.extend(chunk)
                    if len(self.tail) > 8192:
                        del self.tail[:-8192]
                    if self.limit:
                        chunk_tokens = (
                            _num_tokens(chunk.decode("utf-8", "ignore"))
                            if self.is_textual
                            else 0
                        )
                        if chunk_tokens:
                            total, _ = await self.store.adjust(self.user, chunk_tokens)
                            if total > self.limit:
                                await self.store.adjust(self.user, -chunk_tokens)
                                self.quota_exceeded = True
                                logger.warning(
                                    "User %s quota breached mid-stream", self.user
                                )
                                return
                    yield chunk
            finally:
                if self.on_complete:
                    await self.on_complete()

        def get_tail(self) -> bytes:
            return bytes(self.tail)

    class _BufferedResponse(StreamingResponse):
        def __init__(
            self, streamer: "TokenQuotaMiddleware._Streamer", **kwargs
        ) -> None:
            super().__init__(streamer, **kwargs)
            self._streamer = streamer

        async def stream_response(self, send):
            chunks: list[bytes] = []
            async for chunk in self._streamer:
                chunks.append(chunk)
            if getattr(self._streamer, "quota_exceeded", False):
                retry_after = max(
                    0,
                    int(
                        self._streamer.window
                        - (time.time() - getattr(self._streamer, "oldest", 0))
                    ),
                )
                self.status_code = 429
                self.raw_headers = [
                    (b"content-type", b"application/json"),
                    (b"retry-after", str(retry_after).encode()),
                ]
                iterator = async_iter(
                    [
                        json.dumps(
                            {
                                "detail": "token quota exceeded",
                                "retry_after": retry_after,
                            }
                        ).encode()
                    ]
                )
            else:
                iterator = async_iter(chunks)
            await send(
                {
                    "type": "http.response.start",
                    "status": self.status_code,
                    "headers": self.raw_headers,
                }
            )
            async for chunk in iterator:
                if not isinstance(chunk, (bytes, memoryview)):
                    chunk = chunk.encode(self.charset)
                await send(
                    {"type": "http.response.body", "body": chunk, "more_body": True}
                )
            await send({"type": "http.response.body", "body": b"", "more_body": False})

    async def dispatch(self, request: Request, call_next):
        if any(request.url.path.startswith(p) for p in _SKIP_PATHS):
            return await call_next(request)

        if not hasattr(request.app.state, "usage"):
            request.app.state.usage = NullUsageBackend()

        # ── OPTIONAL request-size guard (default 1 MB) ───────────────
        max_bytes = int(os.getenv("MAX_REQUEST_BYTES", "1000000"))
        raw = await request.body()
        if len(raw) > max_bytes:
            return JSONResponse(
                {
                    "detail": "request too large",
                    "limit_bytes": max_bytes,
                },
                status_code=413,
            )

        # Re-use the already-read body from here on
        request._body = raw

        # Fix: Get user from request.state.sub (set by auth middleware)
        user = getattr(request.state, "sub", None) or (
            request.client.host if request.client else "unknown"
        )

        usage = {
            "user": user,
            "project": request.headers.get("x-attach-project", "default"),
            "tokens_in": 0,
            "tokens_out": 0,
            "model": "unknown",
            "request_id": request.headers.get("x-request-id") or str(uuid4()),
        }
        req_is_text = _is_textual(request.headers.get("content-type", ""))

        tokens_in = 0
        if req_is_text:
            # raw already read above
            try:
                payload = json.loads(raw.decode())
            except Exception:
                payload = None
            if isinstance(payload, dict) and "messages" in payload:
                model = payload.get("model", "cl100k_base")
                usage["model"] = model
                tokens_in = num_tokens_from_messages(payload.get("messages", []), model)
            else:
                tokens_in = _num_tokens(raw.decode("utf-8", "ignore"))

        usage["tokens_in"] = tokens_in

        total, oldest = await self.store.adjust(user, tokens_in)
        if self.max_tokens is not None and total > self.max_tokens:
            await self.store.adjust(user, -tokens_in)
            retry_after = max(0, int(self.window - (time.time() - oldest)))
            usage["ts"] = time.time()
            await request.app.state.usage.record(**usage)
            return JSONResponse(
                {"detail": "token quota exceeded", "retry_after": retry_after},
                status_code=429,
            )

        resp = await call_next(request)

        media = resp.media_type or resp.headers.get("content-type", "")
        resp_is_text = _is_textual(media)
        streamer = self._Streamer(
            resp.body_iterator,
            user=user,
            store=self.store,
            max_tokens=self.max_tokens,
            is_textual=resp_is_text,
        )
        streamer.window = self.window
        streamer.oldest = oldest

        headers = dict(resp.headers)
        headers.pop("content-length", None)
        response = self._BufferedResponse(
            streamer,
            status_code=resp.status_code,
            headers=headers,
            media_type=resp.media_type,
        )

        async def finalize() -> None:
            nonlocal tokens_in, oldest
            if getattr(streamer, "quota_exceeded", False):
                usage["detail"] = "token quota exceeded mid-stream"
                retry_after = max(0, int(self.window - (time.time() - oldest)))
                usage["ts"] = time.time()
                await request.app.state.usage.record(**usage)
                return
            tokens_out = 0
            model = usage.get("model", "unknown")
            parsed: dict | None = None
            if resp_is_text:
                # -- Robustly extract the last JSON object -----------------
                text_tail = streamer.get_tail().decode("utf-8", "ignore")
                # 1. Split SSE frames if present: keep only the part after the final "data: "
                if "data:" in text_tail:
                    *_, last_frame = text_tail.strip().split("data:")
                    text_tail = last_frame.strip()
                # 2. Strip the trailing '[DONE]' token if it exists
                if text_tail.endswith("[DONE]"):
                    text_tail = text_tail[: text_tail.rfind("[DONE]")].rstrip()
                # 3. Find the first '{' from the *left* (because the frame has been cleaned)
                brace = text_tail.find("{")
                parsed = None
                if brace != -1:
                    try:
                        parsed = json.loads(text_tail[brace:])
                    except Exception:
                        parsed = None
                if isinstance(parsed, dict):
                    model = parsed.get("model", model)
                    if "usage" in parsed:
                        u = parsed.get("usage") or {}
                        tokens_out = int(u.get("completion_tokens", 0))
                        prompt_tokens = int(u.get("prompt_tokens", tokens_in))
                        delta_prompt = prompt_tokens - tokens_in  # adjust quota window
                        tokens_in = prompt_tokens  # ← canonical value
                        usage["tokens_in"] = tokens_in
                        # Replace provisional count with canonical one in the meter
                        await self.store.adjust(user, delta_prompt)
                    elif "choices" in parsed:
                        msgs = [
                            (c.get("message") or {}).get("content", "")
                            for c in parsed.get("choices", [])
                        ]
                        tokens_out = num_tokens_from_messages(
                            [{"content": m} for m in msgs], model
                        )
                if tokens_out == 0:
                    tokens_out = _num_tokens(text_tail)

            usage["tokens_out"] = tokens_out
            usage["model"] = model

            # All *out* tokens are new – add them once.
            await self.store.adjust(user, tokens_out)

            total = await self.store.peek_total(user)
            if self.max_tokens is not None and total > self.max_tokens:
                retry_after = self.window  # simple worst-case
                response.status_code = 429
                response.headers["Retry-After"] = str(retry_after)
                usage["detail"] = "token quota exceeded post-stream"
                response.headers["content-type"] = "application/json"

            response.headers.update(
                {
                    "x-llm-model": model,
                    "x-tokens-in": str(tokens_in),
                    "x-tokens-out": str(tokens_out),
                }
            )

            usage["ts"] = time.time()
            await request.app.state.usage.record(**usage)
            logger.info(json.dumps(usage))

        streamer.on_complete = finalize
        return response
