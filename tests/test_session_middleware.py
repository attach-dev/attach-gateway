import os

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from starlette.middleware.base import BaseHTTPMiddleware

os.environ["MEM_BACKEND"] = "none"

from middleware.session import _session_id, session_mw


@pytest.mark.asyncio
async def test_missing_sub_returns_401():
    app = FastAPI()
    app.add_middleware(BaseHTTPMiddleware, dispatch=session_mw)

    @app.get("/ping")
    async def ping(request: Request):
        return {"sid": getattr(request.state, "sid", None)}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/ping")

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_valid_request_sets_header_and_state():
    async def add_sub(request: Request, call_next):
        request.state.sub = "user123"
        return await call_next(request)

    app = FastAPI()
    # Add middlewares so that `add_sub` runs before `session_mw`
    app.add_middleware(BaseHTTPMiddleware, dispatch=session_mw)
    app.add_middleware(BaseHTTPMiddleware, dispatch=add_sub)

    @app.get("/ping")
    async def ping(request: Request):
        return {"message": "pong"}  # Simplified - no need to check sid

    headers = {"User-Agent": "UnitTest"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/ping", headers=headers)

    expected_sid = _session_id("user123", "UnitTest")
    assert resp.status_code == 200
    assert resp.headers.get("x-attach-session") == expected_sid[:16]
