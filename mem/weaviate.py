# mem/weaviate.py
"""Simple Weaviate based memory backend."""

from __future__ import annotations

import asyncio
import functools
import os

import weaviate


class WeaviateMemory:
    """Store events in a Weaviate collection."""

    def __init__(self, url: str | None = None):
        url = url or os.getenv("WEAVIATE_URL", "http://localhost:6666")
        # v3 client – simple REST endpoint, no gRPC
        self._client = weaviate.Client(url)

        # ---- ensure class exists (v3 or v4 style) ----
        schema = self._client.schema
        exists = True
        try:
            if hasattr(schema, "contains"):
                exists = schema.contains("MemoryEvent")
            elif hasattr(schema, "get"):
                classes = {c["class"] for c in schema.get().get("classes", [])}
                exists = "MemoryEvent" in classes
        except Exception:
            exists = True

        if not exists and hasattr(schema, "create_class"):
            try:
                schema.create_class({"class": "MemoryEvent"})
            except Exception:
                pass

    async def write(self, event: dict):
        loop = asyncio.get_running_loop()
        # Ensure timestamp matches RFC 3339 if schema expects "date"
        if isinstance(event.get("timestamp"), (int, float)):
            from datetime import datetime, timezone

            event["timestamp"] = datetime.fromtimestamp(
                event["timestamp"], tz=timezone.utc
            ).isoformat(timespec="milliseconds")

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
