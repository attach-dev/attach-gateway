# mem/weaviate.py
"""Simple Weaviate based memory backend."""

from __future__ import annotations

import os
import uuid
import time

import weaviate


class WeaviateMemory:
    """Store events in a Weaviate collection."""

    def __init__(self) -> None:
        # Lazily initialise the client using the configured URL.  This mirrors
        # the previous behaviour of a module level client but keeps it scoped to
        # the class instance.
        self._client = weaviate.Client(os.getenv("WEAVIATE_URL"))

    async def write(self, event: dict) -> None:
        """Add an event object to the ``MemoryEvent`` class."""

        event["id"] = uuid.uuid4().hex
        event["timestamp"] = int(time.time())
        self._client.data_object.create(event, "MemoryEvent", uuid=event["id"])


# Retain module level helper for backwards compatibility
async def write(event: dict) -> None:
    """Write using a default ``WeaviateMemory`` instance."""

    await WeaviateMemory().write(event)
