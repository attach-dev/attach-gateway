"""
Test console auth model.

- /console should be accessible without auth (static HTML)
- /console/static/* should be accessible without auth
- /console/api/* should require JWT Bearer token
"""

import json
import os

import pytest
from httpx import ASGITransport, AsyncClient

os.environ["OIDC_ISSUER"] = "https://test.auth0.com/"
os.environ["OIDC_AUD"] = "test-api"
os.environ["ATTACH_ENABLE_MCP"] = "true"

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

    import attach.audit.sqlite
    import attach.mcp.config

    monkeypatch.setattr(attach.mcp.config, "get_attach_dir", lambda: attach_dir)
    monkeypatch.setattr(attach.audit.sqlite, "get_attach_dir", lambda: attach_dir)

    # Create mcp.json to enable MCP
    mcp_config = {"version": 1, "servers": {}}
    (attach_dir / "mcp.json").write_text(json.dumps(mcp_config))

    # Initialize audit DB
    from attach.audit.sqlite import init_db

    init_db()

    return attach_dir


@pytest.mark.asyncio
async def test_console_landing_page_no_auth(temp_attach_dir):
    """Test that /console is accessible without authentication."""
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Access /console without auth
        response = await client.get("/console")

        # Should return 200 (HTML page loads)
        assert response.status_code == 200
        # Should contain HTML content
        assert (
            b"html" in response.content.lower()
            or b"<!doctype" in response.content.lower()
        )


@pytest.mark.asyncio
async def test_console_static_no_auth(temp_attach_dir):
    """Test that /console/static/* is accessible without authentication."""
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Try to access a static file (even if it doesn't exist, should not get 401)
        response = await client.get("/console/static/app.js")

        # Should either be 200 (file exists) or 404 (file not found), but NOT 401
        assert response.status_code in [200, 404]


@pytest.mark.asyncio
async def test_console_api_requires_auth(temp_attach_dir):
    """Test that /console/api/* requires JWT authentication."""
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Try to access API endpoint without auth
        response = await client.get("/console/api/overview")

        # Should return 401 Unauthorized
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_console_api_with_valid_auth(temp_attach_dir):
    """Test that /console/api/* works with valid JWT."""
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Access API endpoint with valid token
        response = await client.get(
            "/console/api/overview",
            headers={"Authorization": f"Bearer {DUMMY_GOOD_TOKEN}"},
        )

        # Should return 200 and data
        assert response.status_code == 200
        data = response.json()
        assert "calls_today" in data
        assert "denies_today" in data


@pytest.mark.asyncio
async def test_console_api_events_with_auth(temp_attach_dir):
    """Test that /console/api/events requires auth and returns data."""
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Without auth
        response = await client.get("/console/api/events")
        assert response.status_code == 401

        # With valid auth
        response = await client.get(
            "/console/api/events",
            headers={"Authorization": f"Bearer {DUMMY_GOOD_TOKEN}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "events" in data


@pytest.mark.asyncio
async def test_console_api_servers_with_auth(temp_attach_dir):
    """Test that /console/api/servers requires auth and returns data."""
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Without auth
        response = await client.get("/console/api/servers")
        assert response.status_code == 401

        # With valid auth
        response = await client.get(
            "/console/api/servers",
            headers={"Authorization": f"Bearer {DUMMY_GOOD_TOKEN}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "servers" in data
