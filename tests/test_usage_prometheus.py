import os
import sys

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

# Force reload to pick up prometheus_client if just installed
if "usage.backends" in sys.modules:
    del sys.modules["usage.backends"]
if "usage.factory" in sys.modules:
    del sys.modules["usage.factory"]

from middleware.quota import TokenQuotaMiddleware
from usage.factory import get_usage_backend

# At the top, skip test if prometheus_client not available
pytest.importorskip("prometheus_client")  # ← Skip entire test if not installed


@pytest.mark.asyncio
async def test_prometheus_backend_counts_tokens(monkeypatch):
    # Verify we actually get PrometheusUsageBackend
    backend = get_usage_backend("prometheus")
    if not hasattr(backend, "counter"):
        pytest.skip("prometheus_client not available, got NullUsageBackend")

    monkeypatch.setenv("USAGE_METERING", "prometheus")
    monkeypatch.setenv("MAX_TOKENS_PER_MIN", "1000")
    app = FastAPI()
    app.add_middleware(TokenQuotaMiddleware)
    app.state.usage = backend  # Use the backend we verified

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
    # Removed: assert in_val + out_val == sum(c.values.values())
    # The 'values' attribute only exists in the fallback Counter, not the real Prometheus Counter
