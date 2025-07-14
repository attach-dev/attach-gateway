import os

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

pytest.importorskip("tiktoken")

from middleware.quota import TokenQuotaMiddleware


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
