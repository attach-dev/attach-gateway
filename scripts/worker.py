from __future__ import annotations

"""Background worker that processes queued chat requests."""

import asyncio
import json
import os

import httpx

from attach.cache import build_cache, cache_key
from attach.queue import build_queue

ENGINE_URL = os.getenv("ENGINE_URL", "http://localhost:11434").rstrip("/")
CACHE_BACKEND = os.getenv("CACHE_BACKEND", "memory")
QUEUE_BACKEND = os.getenv("QUEUE_BACKEND", "redis")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

cache = build_cache(CACHE_BACKEND, REDIS_URL)
queue = build_queue(QUEUE_BACKEND, REDIS_URL)


async def main() -> None:
    async with httpx.AsyncClient(timeout=None) as client:
        while True:
            job = await queue.get()
            req = job.get("request", {})
            headers = job.get("headers", {})
            key = cache_key(
                req.get("model", ""),
                json.dumps(req.get("messages", [])),
                req.get("params", {}),
            )
            try:
                resp = await client.post(
                    f"{ENGINE_URL}/v1/chat/completions",
                    json=req,
                    headers=headers,
                    timeout=None,
                )
                result = resp.json()
                cache.set(key, result)
            except Exception:
                pass


if __name__ == "__main__":
    asyncio.run(main())
