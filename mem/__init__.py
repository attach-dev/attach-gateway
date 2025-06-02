# mem/__init__.py
import asyncio
import os


class NullMemory:
    async def write(self, event: dict):
        pass


def _load_backend():
    backend = os.getenv("MEM_BACKEND", "none").lower()
    if backend == "weaviate":
        from .weaviate import WeaviateMemory

        return WeaviateMemory()

    return NullMemory()


_memory = _load_backend()


async def write(event: dict):
    # fire-and-forget so proxy latency is unaffected
    asyncio.create_task(_memory.write(event))
