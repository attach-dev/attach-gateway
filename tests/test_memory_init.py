import importlib
import sys
import types

import pytest


@pytest.mark.asyncio
async def test_init_weaviate_backend(monkeypatch):
    """_load_backend() should instantiate WeaviateMemory when MEM_BACKEND=weaviate."""
    monkeypatch.setenv("MEM_BACKEND", "weaviate")

    class DummyMem:
        def __init__(self):
            self.created = True

        async def write(self, event):
            pass

    dummy_mod = types.SimpleNamespace(WeaviateMemory=DummyMem)
    monkeypatch.setitem(sys.modules, "mem.weaviate", dummy_mod)

    mem = importlib.reload(importlib.import_module("mem"))

    assert mem._memory is None
    backend = mem._get_backend()
    assert isinstance(backend, DummyMem)
    assert mem._memory is backend
