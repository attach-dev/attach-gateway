import os

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from middleware.quota import TokenQuotaMiddleware
from usage.factory import get_usage_backend
from usage.metrics import mount_metrics


def setup_module():
    # ✅ Fixed: Use new variable name
    os.environ["USAGE_METERING"] = "prometheus"


@pytest.fixture
def app():
    app = FastAPI()
    mount_metrics(app)
    # ✅ Fixed: Use new variable name
    app.state.usage = get_usage_backend(os.getenv("USAGE_METERING", "null"))
    return app


@pytest.mark.asyncio
async def test_metrics_endpoint(monkeypatch):
    os.environ["MAX_TOKENS_PER_MIN"] = "1000"

    app = FastAPI()
    mount_metrics(app)

    app.add_middleware(TokenQuotaMiddleware)
    app.state.usage = get_usage_backend(os.getenv("USAGE_METERING", "null"))

    @app.post("/echo")
    async def echo(request: Request):
        data = await request.json()
        return {"msg": data.get("msg")}

    transport = ASGITransport(app=app)
    headers = {"X-Attach-User": "bob"}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/echo", json={"msg": "hi"}, headers=headers)
        resp = await client.get("/metrics")

    assert "attach_usage_tokens_total" in resp.text
    assert "bob" in resp.text
