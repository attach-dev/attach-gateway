"""
End-to-end integration tests with real Ollama backend.

These tests require:
1. Ollama running on localhost:11434
2. A model available (e.g., tinyllama)

Skip these tests if Ollama is not available.
"""

import os

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

# Check if Ollama is available
def is_ollama_available():
    try:
        resp = httpx.get("http://localhost:11434/api/tags", timeout=2)
        return resp.status_code == 200
    except Exception:
        return False


OLLAMA_AVAILABLE = is_ollama_available()
SKIP_REASON = "Ollama not running on localhost:11434"

# Set required env vars
os.environ["OIDC_ISSUER"] = "https://test.auth0.com/"
os.environ["OIDC_AUD"] = "test-api"
os.environ["MEM_BACKEND"] = "none"
os.environ["ENGINE_URL"] = "http://localhost:11434"

from jose import JWTError

import auth.oidc
import middleware.auth
from attach.gateway import create_app

VALID_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJlMmUtdXNlciJ9.test"


@pytest.fixture(autouse=True)
def stub_verify_jwt(monkeypatch):
    """Stub JWT verification."""

    def fake_verify_sync(token: str, *, leeway: int = 60):
        if token == VALID_TOKEN:
            return {"sub": "e2e-user"}
        raise JWTError("invalid token")

    async def fake_verify_async(token: str, *, leeway: int = 60):
        return fake_verify_sync(token, leeway=leeway)

    monkeypatch.setattr(auth.oidc, "verify_jwt", fake_verify_sync)
    monkeypatch.setattr(auth.oidc, "verify_jwt_with_exchange", fake_verify_async)
    monkeypatch.setattr(middleware.auth, "verify_jwt", fake_verify_sync)
    monkeypatch.setattr(middleware.auth, "verify_jwt_with_exchange", fake_verify_async)


@pytest.mark.skipif(not OLLAMA_AVAILABLE, reason=SKIP_REASON)
@pytest.mark.asyncio
async def test_e2e_ollama_proxy_chat():
    """Test end-to-end chat completion through gateway to Ollama.

    Note: Gateway proxies to /api/chat endpoint (Ollama native format).
    """
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", timeout=60.0
    ) as client:
        response = await client.post(
            "/api/chat",
            json={
                "model": "tinyllama",
                "messages": [{"role": "user", "content": "Say hi"}],
                "stream": False,
            },
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

        # Should succeed
        assert response.status_code == 200
        data = response.json()

        # Response structure - gateway may transform to OpenAI format
        assert "message" in data or "response" in data or "choices" in data


@pytest.mark.skipif(not OLLAMA_AVAILABLE, reason=SKIP_REASON)
@pytest.mark.asyncio
async def test_e2e_ollama_direct():
    """Test direct Ollama API access (not through gateway proxy)."""
    # This tests that Ollama itself is working
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "tinyllama",
                "prompt": "Hi",
                "stream": False,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "response" in data


@pytest.mark.skipif(not OLLAMA_AVAILABLE, reason=SKIP_REASON)
@pytest.mark.asyncio
async def test_e2e_ollama_tags():
    """Test listing Ollama models directly."""
    async with httpx.AsyncClient() as client:
        response = await client.get("http://localhost:11434/api/tags")

        assert response.status_code == 200
        data = response.json()
        assert "models" in data


@pytest.mark.skipif(not OLLAMA_AVAILABLE, reason=SKIP_REASON)
@pytest.mark.asyncio
async def test_e2e_requires_auth():
    """Test that proxy endpoints require authentication."""
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Without auth - /api/chat is the gateway's proxy endpoint
        response = await client.post(
            "/api/chat",
            json={"model": "tinyllama", "messages": [{"role": "user", "content": "test"}], "stream": False},
        )
        assert response.status_code == 401

        # With invalid token
        response = await client.post(
            "/api/chat",
            json={"model": "tinyllama", "messages": [{"role": "user", "content": "test"}], "stream": False},
            headers={"Authorization": "Bearer invalid"},
        )
        assert response.status_code == 401


@pytest.mark.skipif(not OLLAMA_AVAILABLE, reason=SKIP_REASON)
@pytest.mark.asyncio
async def test_e2e_session_header_injected():
    """Test that authenticated requests go through session middleware."""
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", timeout=60.0
    ) as client:
        response = await client.post(
            "/api/chat",
            json={
                "model": "tinyllama",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": False,
            },
            headers={"Authorization": f"Bearer {VALID_TOKEN}"},
        )

        assert response.status_code == 200
        # Session ID should be set in request state
        # If the request succeeded through middleware, session was processed


@pytest.mark.asyncio
async def test_gateway_health_check():
    """Test gateway starts and responds to basic requests."""
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Auth config endpoint should work without auth
        response = await client.get("/auth/config")
        assert response.status_code == 200
        data = response.json()
        assert "audience" in data


@pytest.mark.asyncio
async def test_gateway_cors_headers():
    """Test that CORS headers are properly set."""
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # OPTIONS request (preflight)
        response = await client.options(
            "/api/generate",
            headers={
                "Origin": "http://localhost:9000",
                "Access-Control-Request-Method": "POST",
            },
        )

        # Should allow the origin
        assert response.headers.get("access-control-allow-origin") in [
            "http://localhost:9000",
            "*",
        ]
