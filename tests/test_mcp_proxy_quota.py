"""
Test MCP proxy and quota enforcement.
"""

import json
import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.middleware.base import BaseHTTPMiddleware

os.environ["OIDC_ISSUER"] = "https://test.auth0.com/"
os.environ["OIDC_AUD"] = "test-api"
os.environ["ATTACH_ENABLE_MCP"] = "true"
os.environ["MEM_BACKEND"] = "none"  # Avoid Weaviate connection in tests

from jose import JWTError

import auth.oidc
import middleware.auth
from attach.gateway import create_app

DUMMY_GOOD_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0LXVzZXIifQ.s3cr3t"
)


@pytest.fixture(autouse=True)
def stub_verify_jwt(monkeypatch):
    """Stub JWT verification."""

    def fake_verify_sync(token: str, *, leeway: int = 60):
        if token == DUMMY_GOOD_TOKEN:
            return {"sub": "test-user"}
        raise JWTError("invalid token")

    async def fake_verify_async(token: str, *, leeway: int = 60):
        if token == DUMMY_GOOD_TOKEN:
            return {"sub": "test-user"}
        raise JWTError("invalid token")

    monkeypatch.setattr(auth.oidc, "verify_jwt", fake_verify_sync)
    monkeypatch.setattr(auth.oidc, "verify_jwt_with_exchange", fake_verify_async)
    monkeypatch.setattr(middleware.auth, "verify_jwt", fake_verify_sync)
    monkeypatch.setattr(middleware.auth, "verify_jwt_with_exchange", fake_verify_async)


@pytest.fixture
def temp_attach_dir(monkeypatch, tmp_path):
    """Override ~/.attach directory with temp dir."""
    attach_dir = tmp_path / "attach"
    attach_dir.mkdir()

    import audit.sqlite
    import mcp.config
    import mcp.quota

    # Patch _attach_dir_path for is_mcp_enabled() and get_mcp_config_path()
    monkeypatch.setattr(mcp.config, "_attach_dir_path", lambda: attach_dir)
    # Also patch get_attach_dir for backward compatibility
    monkeypatch.setattr(mcp.config, "get_attach_dir", lambda: attach_dir)
    monkeypatch.setattr(mcp.quota, "get_attach_dir", lambda: attach_dir)
    monkeypatch.setattr(audit.sqlite, "get_attach_dir", lambda: attach_dir)

    return attach_dir


@pytest.fixture
def fake_mcp_server():
    """A fake MCP upstream server."""
    app = FastAPI()

    @app.post("/mcp")
    async def mcp_endpoint(request):
        body = await request.json()
        # Echo back a successful response
        return {
            "jsonrpc": "2.0",
            "id": body.get("id"),
            "result": {"status": "ok", "method": body.get("method")},
        }

    return app


@pytest.mark.asyncio
async def test_mcp_proxy_forwards_request(temp_attach_dir, fake_mcp_server):
    """Test that MCP proxy forwards requests to upstream."""
    # Configure MCP server
    mcp_config = {
        "version": 1,
        "servers": {
            "test-server": {"enabled": True, "url": "http://fake-upstream/mcp"}
        },
    }
    (temp_attach_dir / "mcp.json").write_text(json.dumps(mcp_config))

    # Initialize audit DB
    from audit.sqlite import init_db

    init_db()

    # Create gateway app
    app = create_app()

    # Mock the httpx client to return fake upstream response
    from unittest.mock import Mock

    import mcp.proxy

    original_client = mcp.proxy.httpx.AsyncClient

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, json, headers):
            # Return a mock response (use Mock, not AsyncMock, since json() is sync)
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.is_success = True
            mock_response.json.return_value = {
                "jsonrpc": "2.0",
                "id": json.get("id"),
                "result": {"status": "ok"},
            }
            return mock_response

    import mcp.proxy

    mcp.proxy.httpx.AsyncClient = MockAsyncClient

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Send request to MCP proxy
            response = await client.post(
                "/mcp/test-server",
                json={"jsonrpc": "2.0", "method": "test/method", "id": 1},
                headers={"Authorization": f"Bearer {DUMMY_GOOD_TOKEN}"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["result"]["status"] == "ok"
    finally:
        mcp.proxy.httpx.AsyncClient = original_client


@pytest.mark.asyncio
async def test_mcp_quota_enforcement(temp_attach_dir):
    """Test that quota enforcement denies requests when limit is exceeded."""
    # Configure MCP server
    mcp_config = {
        "version": 1,
        "servers": {
            "test-server": {"enabled": True, "url": "http://fake-upstream/mcp"}
        },
    }
    (temp_attach_dir / "mcp.json").write_text(json.dumps(mcp_config))

    # Configure quota policy with limit of 1
    policy_config = {
        "version": 1,
        "enabled": True,
        "per_user_daily_tool_calls": {"*": 1},
    }
    (temp_attach_dir / "mcp_policy.json").write_text(json.dumps(policy_config))

    # Initialize audit DB
    from audit.sqlite import init_db

    init_db()

    # Create gateway app
    app = create_app()

    # Mock httpx client
    from unittest.mock import Mock

    import mcp.proxy

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, json, headers):
            # Use Mock, not AsyncMock, since json() is sync in httpx
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.is_success = True
            mock_response.json.return_value = {
                "jsonrpc": "2.0",
                "id": json.get("id"),
                "result": {"status": "ok"},
            }
            return mock_response

    original_client = mcp.proxy.httpx.AsyncClient
    mcp.proxy.httpx.AsyncClient = MockAsyncClient

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # First tools/call should succeed
            response1 = await client.post(
                "/mcp/test-server",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {"name": "test.tool"},
                    "id": 1,
                },
                headers={"Authorization": f"Bearer {DUMMY_GOOD_TOKEN}"},
            )

            assert response1.status_code == 200
            data1 = response1.json()
            assert "result" in data1  # Should succeed

            # Second tools/call should be denied (quota exceeded)
            response2 = await client.post(
                "/mcp/test-server",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {"name": "test.tool"},
                    "id": 2,
                },
                headers={"Authorization": f"Bearer {DUMMY_GOOD_TOKEN}"},
            )

            assert response2.status_code == 200  # JSON-RPC error is still HTTP 200
            data2 = response2.json()
            assert "error" in data2
            assert data2["error"]["code"] == -32029  # quota exceeded code
    finally:
        mcp.proxy.httpx.AsyncClient = original_client


@pytest.mark.asyncio
async def test_mcp_server_not_found(temp_attach_dir):
    """Test that requesting unknown server returns 404."""
    # Configure empty MCP
    mcp_config = {"version": 1, "servers": {}}
    (temp_attach_dir / "mcp.json").write_text(json.dumps(mcp_config))

    # Initialize audit DB
    from audit.sqlite import init_db

    init_db()

    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/mcp/nonexistent",
            json={"jsonrpc": "2.0", "method": "test", "id": 1},
            headers={"Authorization": f"Bearer {DUMMY_GOOD_TOKEN}"},
        )

        assert response.status_code == 404
        data = response.json()
        assert "error" in data
