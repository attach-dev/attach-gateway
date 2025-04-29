import pytest
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import HTTPException
from httpx import AsyncClient, ASGITransport
from jose import JWTError

import auth.oidc 
from auth.oidc import verify_jwt
from middleware.auth import jwt_auth_mw

# Example of a dummy JWT with three segments
DUMMY_GOOD_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0LXVzZXIifQ.s3cr3t"
DUMMY_BAD_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.payload"

@pytest.fixture(autouse=True)
def stub_verify_jwt(monkeypatch):
    """
    Replace the real verify_jwt() with a fake that:
    - returns {"sub": "test-user"} for token "DUMMY_GOOD_TOKEN"
    - raises ValueError for anything else
    """
    def fake_verify(token: str, *, leeway: int = 60):
        if token == DUMMY_GOOD_TOKEN:
            return {"sub": "test-user"}
        raise JWTError("invalid token")

    # patch the original
    monkeypatch.setattr(auth.oidc, "verify_jwt", fake_verify)
    # patch the copy inside the middleware module
    import middleware.auth
    monkeypatch.setattr(middleware.auth, "verify_jwt", fake_verify)


@pytest.fixture
def app():
    """
    A minimal FastAPI app that installs our JWT middleware
    and exposes one protected endpoint.
    """
    app = FastAPI()
    app.add_middleware(BaseHTTPMiddleware, dispatch=jwt_auth_mw)

    @app.get("/protected")
    async def protected(request: Request):
        # Echo back the sub that our middleware put on state
        return {"sub": request.state.sub}

    return app


@pytest.mark.asyncio
async def test_no_token_gives_401(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/protected")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Missing Bearer token"


@pytest.mark.asyncio
async def test_bad_token_gives_401(app):
    headers = {"Authorization": f"Bearer {DUMMY_BAD_TOKEN}"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/protected", headers=headers)
    assert resp.status_code == 401
    assert "invalid token" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_good_token_succeeds_and_sets_sub(app):
    headers = {"Authorization": f"Bearer {DUMMY_GOOD_TOKEN}"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/protected", headers=headers)
    assert resp.status_code == 200
    assert resp.json().get("sub") == "test-user"