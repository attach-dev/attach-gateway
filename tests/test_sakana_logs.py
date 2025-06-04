import os
import types

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

os.environ["MEM_BACKEND"] = "none"

import logs
import mem.sakana as sakana


@pytest.fixture
def app(monkeypatch):
    app = FastAPI()
    app.include_router(logs.router)
    return app


@pytest.mark.asyncio
async def test_post_log_accepted(monkeypatch, app):
    called = {}

    async def fake_write(event):
        called["event"] = event

    monkeypatch.setattr(logs, "sakana_write", fake_write)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/logs", json={"run_id": "r1", "level": "info", "message": "hi"}
        )

    assert resp.status_code == 202
    assert called["event"]["run_id"] == "r1"
    assert called["event"]["level"] == "info"
    assert called["event"]["message"] == "hi"
    assert isinstance(called["event"]["timestamp"], float)


@pytest.mark.asyncio
async def test_validation_error_returns_422(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/v1/logs", json={"level": "info", "message": "hi"})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_integration_stores_in_weaviate(monkeypatch):
    recorded = {}

    class DummyCollection:
        def insert(self, document):
            recorded["event"] = document

        def __init__(self):
            self.data = types.SimpleNamespace(insert=self.insert)

    class DummyClient:
        def __init__(self, url=None):
            self.collections = types.SimpleNamespace(get=self.get)

        def get(self, name):
            recorded["class"] = name
            return DummyCollection()

    import mem.weaviate as wv

    monkeypatch.setattr(wv, "WeaviateClient", DummyClient)

    event = {"run_id": "123", "level": "info", "message": "test"}
    await sakana.write(event)

    assert recorded["class"] == "MemoryEvent"
    assert "id" in recorded["event"]
    assert "timestamp" in recorded["event"]
    assert recorded["event"]["level"] == "info"
