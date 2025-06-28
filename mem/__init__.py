# mem/__init__.py

import asyncio
import os
from typing import Protocol


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
        from .weaviate import WeaviateMemory  # local import to avoid deps if unused

        # Try config first, fall back to env var (backwards compatible)
        if config and config.weaviate_url:
            return WeaviateMemory(config.weaviate_url)
        return WeaviateMemory()

    return NullMemory()


# --- lazy singleton ---------------------------------------------------------
_memory: MemoryBackend | None = None


def _get_backend() -> MemoryBackend:
    global _memory
    if _memory is None:
        _memory = _build_backend()  # Works with no arguments
    return _memory


# public helpers -------------------------------------------------------------
async def write(event: dict):
    """Fire-and-forget write; never blocks caller."""
    asyncio.create_task(_get_backend().write(event))


def get_memory_backend(kind: str = "none", config=None):
    """Explicit factory used by attach.gateway.create_app."""
    return _build_backend(kind, config)  # Works with config
