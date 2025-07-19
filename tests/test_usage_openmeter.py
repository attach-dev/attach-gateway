import os
import sys
import types

import pytest


class DummyEvents:
    def __init__(self):
        self.called = None

    async def create(self, **event):
        self.called = event


class DummyClient:
    def __init__(self, api_key: str, base_url: str = "https://openmeter.cloud") -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.events = DummyEvents()

    async def aclose(self) -> None:
        pass


dummy_module = types.SimpleNamespace(Client=DummyClient)


@pytest.mark.asyncio
async def test_openmeter_backend_create(monkeypatch):
    monkeypatch.setitem(sys.modules, "openmeter", dummy_module)
    if "usage.backends" in sys.modules:
        del sys.modules["usage.backends"]
    if "usage.factory" in sys.modules:
        del sys.modules["usage.factory"]
    from usage.factory import get_usage_backend

    monkeypatch.setenv("OPENMETER_API_KEY", "k")
    monkeypatch.setenv("OPENMETER_URL", "https://example.com")

    backend = get_usage_backend("openmeter")
    assert backend.__class__.__name__ == "OpenMeterBackend"
    await backend.record(user="bob", tokens_in=1, tokens_out=2, model="m")
    await backend.aclose()

    called = backend.client.events.called
    assert called["type"] == "tokens"
    assert called["subject"] == "bob"
    assert called["project"] is None
    assert called["data"] == {"tokens_in": 1, "tokens_out": 2, "model": "m"}
    assert "time" in called


def test_openmeter_backend_missing_key(monkeypatch):
    monkeypatch.setitem(sys.modules, "openmeter", dummy_module)
    if "usage.backends" in sys.modules:
        del sys.modules["usage.backends"]
    if "usage.factory" in sys.modules:
        del sys.modules["usage.factory"]
    from usage.factory import get_usage_backend

    monkeypatch.setenv("USAGE_METERING", "openmeter")
    monkeypatch.delenv("OPENMETER_API_KEY", raising=False)

    backend = get_usage_backend("openmeter")
    assert backend.__class__.__name__ == "NullUsageBackend"
