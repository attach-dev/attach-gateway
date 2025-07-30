from __future__ import annotations

"""Simple runtime-swappable FIFO job queue."""

import asyncio
import json
import uuid
from typing import Any, Optional

import redis


class _MemoryQueue:
    """Asyncio-based in-memory queue."""

    def __init__(self) -> None:
        self._q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def put(self, job: dict[str, Any]) -> None:
        await self._q.put(job)

    async def get(self) -> dict[str, Any]:
        job = await self._q.get()
        self._q.task_done()
        return job


class _RedisQueue:
    """Redis-backed job queue."""

    def __init__(self, url: str, name: str = "attach:queue") -> None:
        self._client = redis.Redis.from_url(url)
        self._name = name

    async def put(self, job: dict[str, Any]) -> None:
        loop = asyncio.get_running_loop()
        data = json.dumps(job)
        await loop.run_in_executor(None, self._client.lpush, self._name, data)

    async def get(self) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        key, data = await loop.run_in_executor(None, self._client.brpop, self._name, 0)
        return json.loads(data)


def build_queue(kind: str = "memory", redis_url: Optional[str] = None) -> Any:
    """Return a queue instance for ``kind``."""

    kind = (kind or "memory").lower()
    if kind == "redis":
        url = redis_url or "redis://localhost:6379/0"
        return _RedisQueue(url)
    return _MemoryQueue()


def new_job(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a new job dictionary with a unique ID."""

    job = {"id": uuid.uuid4().hex}
    job.update(payload)
    return job
