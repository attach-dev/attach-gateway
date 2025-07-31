"""
Stateless JWT authentication middleware.

This file *must* live inside the project's `middleware/` package so that
`from middleware.auth import jwt_auth_mw` works.
"""
from __future__ import annotations

import os

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from auth.oidc import verify_jwt, verify_jwt_with_exchange  # your existing verifier (RS256 / ES256 only)

_CLOCK_SKEW = 60  # seconds

# Paths that don't require authentication
EXCLUDED_PATHS = {
    "/auth/config",
    "/docs",
    "/redoc",
    "/openapi.json",
}


async def jwt_auth_mw(request: Request, call_next):
    """
    • Extracts the Bearer token from the `Authorization` header.
    • Verifies it with `auth.oidc.verify_jwt`.
    • Stores the `sub` claim in `request.state.sub` for downstream middleware.
    • Rejects the request with 401 on any failure.
    • Skips authentication for excluded paths and OPTIONS requests.
    """
    # Skip authentication for OPTIONS requests (CORS preflight)
    if request.method == "OPTIONS":
        return await call_next(request)
    
    # Skip authentication for excluded paths
    if request.url.path in EXCLUDED_PATHS:
        return await call_next(request)

    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"detail": "Missing Bearer token"})

    token = auth_header.split(" ", 1)[1]

    try:
        # Use sync version unless Descope exchange is explicitly enabled
        if os.getenv("ENABLE_DESCOPE_EXCHANGE", "false").lower() == "true":
            claims = await verify_jwt_with_exchange(token, leeway=_CLOCK_SKEW) 
        else:
            claims = verify_jwt(token, leeway=_CLOCK_SKEW)  # original sync version
    except Exception as exc:
        return JSONResponse(status_code=401, content={"detail": str(exc)})

    # attach the user id (sub) for the session-middleware
    request.state.sub = claims["sub"]
    return await call_next(request)
