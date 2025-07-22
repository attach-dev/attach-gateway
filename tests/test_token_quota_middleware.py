import os

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

pytest.importorskip("tiktoken")

from starlette.responses import StreamingResponse

from middleware.quota import InMemoryMeterStore, TokenQuotaMiddleware


@pytest.mark.asyncio
async def test_under_limit_passes():
    os.environ["MAX_TOKENS_PER_MIN"] = "100"
    app = FastAPI()
    app.add_middleware(TokenQuotaMiddleware)

    @app.post("/echo")
    async def echo(request: Request):
        data = await request.json()
        return {"msg": data.get("msg")}

    headers = {"X-Attach-User": "alice"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/echo", json={"msg": "hi"}, headers=headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_over_limit_returns_429():
    os.environ["MAX_TOKENS_PER_MIN"] = "1"
    app = FastAPI()
    app.add_middleware(TokenQuotaMiddleware)

    @app.post("/echo")
    async def echo(request: Request):
        data = await request.json()
        return {"msg": data.get("msg")}

    headers = {"X-Attach-User": "bob"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/echo", json={"msg": "hello"}, headers=headers)
    assert resp.status_code == 429
    assert "retry_after" in resp.json()


@pytest.mark.asyncio
async def test_midstream_over_limit_rolls_back(monkeypatch):
    monkeypatch.setenv("MAX_TOKENS_PER_MIN", "5")
    store = InMemoryMeterStore()
    app = FastAPI()
    app.add_middleware(TokenQuotaMiddleware, store=store)

    @app.get("/stream")
    async def stream():
        async def gen():
            yield b"hi"
            yield b"aaaaaaa"

        return StreamingResponse(gen(), media_type="text/plain")

    headers = {"X-Attach-User": "carol"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/stream", headers=headers)

    assert resp.status_code == 429
    assert resp.json()["detail"] == "token quota exceeded"
    total = await store.peek_total("carol")
    assert total == 2
