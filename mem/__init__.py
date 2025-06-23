# mem/__init__.py  (replace the existing file)

import asyncio, os
from typing import Optional, Protocol


class MemoryBackend(Protocol):
    async def write(self, event: dict): ...
    # add read/query interfaces later


class NullMemory:
    async def write(self, event: dict):
        # swallow silently
        return None


def _build_backend(kind: str | None = None, config=None) -> MemoryBackend:
    kind = (kind or os.getenv("MEM_BACKEND", "none")).lower()

    if kind == "weaviate":
        from .weaviate import WeaviateMemory   # local import to avoid deps if unused
        # Try config first, fall back to env var (backwards compatible)
        if config and config.weaviate_url:
            weaviate_url = config.weaviate_url
        else:
            weaviate_url = os.getenv("WEAVIATE_URL", "http://localhost:6666")
        return WeaviateMemory(weaviate_url)

    return NullMemory()


# --- lazy singleton ---------------------------------------------------------
_backend: Optional[MemoryBackend] = None


def _get_backend() -> MemoryBackend:
    global _backend
    if _backend is None:
        _backend = _build_backend()  # Works with no arguments
    return _backend


# public helpers -------------------------------------------------------------
async def write(event: dict):
    """Fire-and-forget write; never blocks caller."""
    asyncio.create_task(_get_backend().write(event))


def get_memory_backend(kind: str = "none", config=None):
    """Explicit factory used by attach.gateway.create_app."""
    return _build_backend(kind, config)  # Works with config