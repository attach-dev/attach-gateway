# mem/__init__.py
import os, asyncio, json, time, importlib

class NullMemory:
    async def write(self, event: dict): pass

def _load_backend():
    backend = os.getenv("MEM_BACKEND", "none").lower()
    if backend == "weaviate":
        return importlib.import_module("mem.weaviate").WeaviateMemory()
    return NullMemory()

_memory = _load_backend()

async def write(event: dict):
    # fire-and-forget so proxy latency is unaffected
    asyncio.create_task(_memory.write(event))
