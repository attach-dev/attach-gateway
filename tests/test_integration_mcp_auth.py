"""
Integration tests for MCP Gateway with auth, quota, and multi-tenant features.

Tests verify:
1. MCP endpoints require JWT authentication
2. MCP quota enforcement across multiple users
3. Console API auth model (public landing, protected API)
4. Multi-tenant user isolation in audit logs
5. Token exchange flow (Descope/Auth0)
"""

import json
import os
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

# Set required env vars before importing gateway
os.environ["OIDC_ISSUER"] = "https://test.auth0.com/"
os.environ["OIDC_AUD"] = "test-api"
os.environ["ATTACH_ENABLE_MCP"] = "true"
os.environ["MEM_BACKEND"] = "none"

from jose import JWTError

import auth.oidc
import middleware.auth
from attach.gateway import create_app

# Test tokens for different users
USER_ALICE_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhbGljZSJ9.test1"
USER_BOB_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJib2IifQ.test2"
USER_CHARLIE_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJjaGFybGllIn0.test3"
INVALID_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJiYWQifQ.invalid"


@pytest.fixture(autouse=True)
def stub_verify_jwt(monkeypatch):
    """Stub JWT verification to allow test tokens."""

    def fake_verify_sync(token: str, *, leeway: int = 60):
        token_map = {
            USER_ALICE_TOKEN: {"sub": "alice"},
            USER_BOB_TOKEN: {"sub": "bob"},
            USER_CHARLIE_TOKEN: {"sub": "charlie"},
        }
        if token in token_map:
            return token_map[token]
        raise JWTError("invalid token")

    async def fake_verify_async(token: str, *, leeway: int = 60):
        return fake_verify_sync(token, leeway=leeway)

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
    import attach.mcp.quota

    monkeypatch.setattr(attach.mcp.config, "_attach_dir_path", lambda: attach_dir)
    monkeypatch.setattr(attach.mcp.config, "get_attach_dir", lambda: attach_dir)
    monkeypatch.setattr(attach.mcp.quota, "get_attach_dir", lambda: attach_dir)
    monkeypatch.setattr(attach.audit.sqlite, "get_attach_dir", lambda: attach_dir)

    return attach_dir


@pytest.fixture
def setup_mcp_servers(temp_attach_dir):
    """Configure MCP servers for testing."""
    mcp_config = {
        "version": 1,
        "servers": {
            "github": {"enabled": True, "url": "http://mock-github/mcp"},
            "notion": {"enabled": True, "url": "http://mock-notion/mcp"},
            "disabled-server": {"enabled": False, "url": "http://mock-disabled/mcp"},
        },
    }
    (temp_attach_dir / "mcp.json").write_text(json.dumps(mcp_config))
    return mcp_config


@pytest.fixture
def setup_quota_policy(temp_attach_dir):
    """Configure quota policy for testing."""
    policy = {
        "version": 1,
        "enabled": True,
        "per_user_daily_tool_calls": {
            "github.*": 5,
            "notion.*": 3,
            "*": 10,
        },
    }
    (temp_attach_dir / "mcp_policy.json").write_text(json.dumps(policy))
    return policy


@pytest.fixture
def init_audit_db(temp_attach_dir):
    """Initialize audit database."""
    from attach.audit.sqlite import init_db

    init_db()


@pytest.fixture
def mock_mcp_upstream(monkeypatch):
    """Mock MCP upstream servers."""
    from unittest.mock import Mock

    import attach.mcp.proxy

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, json, headers):
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.is_success = True
            mock_response.json.return_value = {
                "jsonrpc": "2.0",
                "id": json.get("id"),
                "result": {"status": "ok", "server": url},
            }
            return mock_response

    original = attach.mcp.proxy.httpx.AsyncClient
    attach.mcp.proxy.httpx.AsyncClient = MockAsyncClient
    yield
    attach.mcp.proxy.httpx.AsyncClient = original


# ============================================================================
# Test: Authentication Requirements
# ============================================================================


@pytest.mark.asyncio
async def test_mcp_list_requires_auth(temp_attach_dir, setup_mcp_servers, init_audit_db):
    """Test that /mcp endpoint requires JWT authentication."""
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Without auth
        response = await client.get("/mcp")
        assert response.status_code == 401

        # With invalid token
        response = await client.get(
            "/mcp", headers={"Authorization": f"Bearer {INVALID_TOKEN}"}
        )
        assert response.status_code == 401

        # With valid token
        response = await client.get(
            "/mcp", headers={"Authorization": f"Bearer {USER_ALICE_TOKEN}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "servers" in data
        assert "github" in data["servers"]
        assert "notion" in data["servers"]
        # Disabled server should not appear
        assert "disabled-server" not in data["servers"]


@pytest.mark.asyncio
async def test_mcp_proxy_requires_auth(
    temp_attach_dir, setup_mcp_servers, init_audit_db, mock_mcp_upstream
):
    """Test that /mcp/{server} proxy requires JWT authentication."""
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        payload = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}

        # Without auth
        response = await client.post("/mcp/github", json=payload)
        assert response.status_code == 401

        # With valid token
        response = await client.post(
            "/mcp/github",
            json=payload,
            headers={"Authorization": f"Bearer {USER_ALICE_TOKEN}"},
        )
        assert response.status_code == 200


# ============================================================================
# Test: Multi-Tenant User Isolation
# ============================================================================


@pytest.mark.asyncio
async def test_multi_tenant_audit_isolation(
    temp_attach_dir, setup_mcp_servers, init_audit_db, mock_mcp_upstream
):
    """Test that audit logs properly isolate different users."""
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Alice makes a request
        await client.post(
            "/mcp/github",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "github.create_issue"},
                "id": 1,
            },
            headers={"Authorization": f"Bearer {USER_ALICE_TOKEN}"},
        )

        # Bob makes a request
        await client.post(
            "/mcp/notion",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "notion.create_page"},
                "id": 2,
            },
            headers={"Authorization": f"Bearer {USER_BOB_TOKEN}"},
        )

    # Query audit logs
    from attach.audit.sqlite import query_mcp_events

    all_events = query_mcp_events(limit=100)
    assert len(all_events) >= 2

    alice_events = query_mcp_events(limit=100, user="alice")
    bob_events = query_mcp_events(limit=100, user="bob")

    # Verify isolation
    assert len(alice_events) >= 1
    assert len(bob_events) >= 1
    assert all(e["user"] == "alice" for e in alice_events)
    assert all(e["user"] == "bob" for e in bob_events)


# ============================================================================
# Test: Per-User Quota Enforcement
# ============================================================================


@pytest.mark.asyncio
async def test_per_user_quota_isolation(
    temp_attach_dir, setup_mcp_servers, setup_quota_policy, init_audit_db, mock_mcp_upstream
):
    """Test that quota is enforced per-user, not globally."""
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Alice exhausts her notion quota (limit=3)
        for i in range(3):
            response = await client.post(
                "/mcp/notion",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {"name": "notion.create_page"},
                    "id": i + 1,
                },
                headers={"Authorization": f"Bearer {USER_ALICE_TOKEN}"},
            )
            assert response.status_code == 200
            data = response.json()
            assert "result" in data  # Should succeed

        # Alice's 4th request should be denied
        response = await client.post(
            "/mcp/notion",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "notion.create_page"},
                "id": 100,
            },
            headers={"Authorization": f"Bearer {USER_ALICE_TOKEN}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == -32029  # quota exceeded

        # But Bob should still be able to use notion (his own quota)
        response = await client.post(
            "/mcp/notion",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "notion.create_page"},
                "id": 200,
            },
            headers={"Authorization": f"Bearer {USER_BOB_TOKEN}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "result" in data  # Should succeed (Bob's own quota)


@pytest.mark.asyncio
async def test_quota_glob_patterns(
    temp_attach_dir, setup_mcp_servers, setup_quota_policy, init_audit_db, mock_mcp_upstream
):
    """Test that quota glob patterns work correctly.

    Note: Quota counts per exact tool name, not per pattern.
    So calling github.create_issue 5 times = 5 calls toward github.* limit.
    """
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # GitHub tools have limit=5, call same tool 5 times
        for i in range(5):
            response = await client.post(
                "/mcp/github",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {"name": "github.create_issue"},
                    "id": i + 1,
                },
                headers={"Authorization": f"Bearer {USER_CHARLIE_TOKEN}"},
            )
            assert response.status_code == 200
            data = response.json()
            assert "result" in data

        # 6th call to same tool should be denied
        response = await client.post(
            "/mcp/github",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "github.create_issue"},
                "id": 999,
            },
            headers={"Authorization": f"Bearer {USER_CHARLIE_TOKEN}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == -32029


# ============================================================================
# Test: Console Auth Model
# ============================================================================


@pytest.mark.asyncio
async def test_console_public_vs_protected(temp_attach_dir, setup_mcp_servers, init_audit_db):
    """Test console auth model: public landing, protected API."""
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Public endpoints (no auth required)
        response = await client.get("/console")
        assert response.status_code == 200

        response = await client.get("/console/static/app.js")
        # 200 or 404 (file may not exist), but NOT 401
        assert response.status_code in [200, 404]

        # Protected API endpoints
        response = await client.get("/console/api/overview")
        assert response.status_code == 401

        response = await client.get("/console/api/events")
        assert response.status_code == 401

        response = await client.get("/console/api/servers")
        assert response.status_code == 401

        # With valid auth
        response = await client.get(
            "/console/api/overview",
            headers={"Authorization": f"Bearer {USER_ALICE_TOKEN}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "calls_today" in data
        assert "denies_today" in data


# ============================================================================
# Test: Disabled MCP (Opt-Out)
# ============================================================================


@pytest.mark.asyncio
async def test_mcp_disabled_no_routes(monkeypatch, tmp_path):
    """Test that MCP routes are not mounted when disabled."""
    attach_dir = tmp_path / "attach_disabled"
    attach_dir.mkdir()

    import attach.mcp.config

    monkeypatch.setattr(attach.mcp.config, "_attach_dir_path", lambda: attach_dir)
    monkeypatch.delenv("ATTACH_ENABLE_MCP", raising=False)

    # No mcp.json, no env var = MCP disabled
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/mcp", headers={"Authorization": f"Bearer {USER_ALICE_TOKEN}"}
        )
        assert response.status_code == 404

        response = await client.get("/console")
        assert response.status_code == 404


# ============================================================================
# Test: Server Not Found / Disabled
# ============================================================================


@pytest.mark.asyncio
async def test_mcp_server_not_found(
    temp_attach_dir, setup_mcp_servers, init_audit_db
):
    """Test requesting a non-existent MCP server."""
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/mcp/nonexistent",
            json={"jsonrpc": "2.0", "method": "test", "id": 1},
            headers={"Authorization": f"Bearer {USER_ALICE_TOKEN}"},
        )
        assert response.status_code == 404
        data = response.json()
        assert "error" in data


@pytest.mark.asyncio
async def test_mcp_disabled_server(
    temp_attach_dir, setup_mcp_servers, init_audit_db
):
    """Test requesting a disabled MCP server."""
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/mcp/disabled-server",
            json={"jsonrpc": "2.0", "method": "test", "id": 1},
            headers={"Authorization": f"Bearer {USER_ALICE_TOKEN}"},
        )
        assert response.status_code == 404
        data = response.json()
        assert "error" in data
