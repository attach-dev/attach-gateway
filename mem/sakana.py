from __future__ import annotations

from mem.weaviate import write as _weaviate_write


async def write(event: dict) -> None:
    """Persist a Sakana log event using the Weaviate memory backend."""
    # TODO: buffer events and batch writes if log volume becomes high
    await _weaviate_write(event)
