# mem/weaviate.py
"""Simple Weaviate based memory backend."""

from __future__ import annotations

import asyncio
import functools

import weaviate


class WeaviateMemory:
    """Store events in a Weaviate collection."""

    def __init__(self, url: str = "http://localhost:6666"):
        # v3 client – simple REST endpoint, no gRPC
        self._client = weaviate.Client(url)

        # ---- ensure class exists (v3 style) ----
        classes = {c["class"] for c in self._client.schema.get().get("classes", [])}
        if "MemoryEvent" not in classes:
            print("⚠️  No MemoryEvent class yet (run a chat first)")
            exit(0)

    async def write(self, event: dict):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            functools.partial(
                self._client.data_object.create,
                data_object=event,
                class_name="MemoryEvent",
            ),
        )


# Retain module level helper for backwards compatibility
async def write(event: dict) -> None:
    """Write using a default ``WeaviateMemory`` instance."""

    await WeaviateMemory().write(event)
