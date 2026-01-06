"""
Test MCP opt-in behavior.

Ensure that without ATTACH_ENABLE_MCP=true or ~/.attach/mcp.json,
the /mcp and /console routes are not mounted (404).
"""

import os
import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

# Set required env vars before importing gateway
os.environ["OIDC_ISSUER"] = "https://test.auth0.com/"
os.environ["OIDC_AUD"] = "test-api"

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

    import mcp.config

    monkeypatch.setattr(mcp.config, "get_attach_dir", lambda: attach_dir)

    return attach_dir


@pytest.mark.asyncio
async def test_mcp_disabled_by_default(temp_attach_dir, monkeypatch):
    """
    Without ATTACH_ENABLE_MCP or mcp.json,
    /mcp and /console should be 404.
    """
    # Ensure MCP is not enabled
    monkeypatch.delenv("ATTACH_ENABLE_MCP", raising=False)

    # Create app without MCP enabled
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Test /mcp endpoint
        response = await client.get(
            "/mcp", headers={"Authorization": f"Bearer {DUMMY_GOOD_TOKEN}"}
        )
        assert response.status_code == 404

        # Test /console endpoint (should also be 404)
        response = await client.get("/console")
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_mcp_enabled_via_env(temp_attach_dir, monkeypatch):
    """
    With ATTACH_ENABLE_MCP=true,
    /mcp and /console should be available.
    """
    monkeypatch.setenv("ATTACH_ENABLE_MCP", "true")

    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Test /mcp endpoint (should return 200 with servers list)
        response = await client.get(
            "/mcp", headers={"Authorization": f"Bearer {DUMMY_GOOD_TOKEN}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "servers" in data

        # Test /console endpoint (should return 200 with HTML)
        response = await client.get("/console")
        assert response.status_code == 200
        assert (
            b"Attach Gateway" in response.content
            or b"console" in response.content.lower()
        )


@pytest.mark.asyncio
async def test_mcp_enabled_via_config_file(temp_attach_dir, monkeypatch):
    """
    With ~/.attach/mcp.json present,
    /mcp and /console should be available.
    """
    monkeypatch.delenv("ATTACH_ENABLE_MCP", raising=False)

    # Create mcp.json config file
    mcp_json_path = temp_attach_dir / "mcp.json"
    mcp_json_path.write_text('{"version": 1, "servers": {}}')

    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Test /mcp endpoint
        response = await client.get(
            "/mcp", headers={"Authorization": f"Bearer {DUMMY_GOOD_TOKEN}"}
        )
        assert response.status_code == 200

        # Test /console endpoint
        response = await client.get("/console")
        assert response.status_code == 200
