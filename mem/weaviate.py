# mem/weaviate.py
"""Simple Weaviate based memory backend."""

from __future__ import annotations

import os
import time
import uuid

from weaviate import WeaviateClient
from weaviate.collections import Collection
from weaviate.connect import ConnectionParams


class WeaviateMemory:
    """Store events in a Weaviate collection."""

    def __init__(self) -> None:
        # Lazily initialise the client using the configured URL.  This mirrors
        # the previous behaviour of a module level client but keeps it scoped to
        # the class instance.
        http_url = os.getenv("WEAVIATE_URL", "http://127.0.0.1:6666")
        grpc_port = int(os.getenv("WEAVIATE_GRPC_PORT", 50051))
        params = ConnectionParams.from_url(http_url, grpc_port=grpc_port)
        self._client = WeaviateClient(connection_params=params)
        self._collection: Collection = self._client.collections.get("MemoryEvent")

    async def write(self, event: dict) -> None:
        """Add an event object to the ``MemoryEvent`` class."""

        event["id"] = uuid.uuid4().hex
        event["timestamp"] = int(time.time())
        self._collection.data.insert(event)


# Retain module level helper for backwards compatibility
async def write(event: dict) -> None:
    """Write using a default ``WeaviateMemory`` instance."""

    await WeaviateMemory().write(event)
