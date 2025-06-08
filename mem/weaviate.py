# mem/weaviate.py
"""Simple Weaviate based memory backend."""

from __future__ import annotations

import asyncio
import functools

import weaviate


class WeaviateMemory:
    """Store events in a Weaviate collection."""

    def __init__(self, url: str = "http://localhost:6666"):
        self._client = weaviate.Client(url)
        # ensure schema is present once at start-up
        if not self._client.schema.contains({"class": "MemoryEvent"}):
            self._client.schema.create_class(
                {
                    "class": "MemoryEvent",
                    "properties": [
                        {"name": "timestamp", "dataType": ["date"]},
                        {"name": "role", "dataType": ["text"]},
                        {"name": "content", "dataType": ["text"]},
                    ],
                }
            )

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
