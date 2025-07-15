import os

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from middleware.quota import TokenQuotaMiddleware
from usage.factory import get_usage_backend


@pytest.mark.asyncio
async def test_prometheus_backend_counts_tokens(monkeypatch):
    os.environ["USAGE_BACKEND"] = "prometheus"
    os.environ["MAX_TOKENS_PER_MIN"] = "1000"
    app = FastAPI()
    app.add_middleware(TokenQuotaMiddleware)
    app.state.usage = get_usage_backend(os.getenv("USAGE_BACKEND", "null"))

    @app.post("/echo")
    async def echo(request: Request):
        data = await request.json()
        return {"msg": data.get("msg")}

    transport = ASGITransport(app=app)
    headers = {"X-Attach-User": "bob"}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/echo", json={"msg": "hi"}, headers=headers)
        await client.post("/echo", json={"msg": "there"}, headers=headers)

    c = app.state.usage.counter
    in_val = c.labels(user="bob", direction="in", model="unknown")._value.get()
    out_val = c.labels(user="bob", direction="out", model="unknown")._value.get()
    assert in_val > 0
    assert out_val > 0
    assert in_val + out_val == sum(c.values.values())
