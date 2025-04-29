"""
Stateless JWT authentication middleware.

This file *must* live inside the project's `middleware/` package so that
`from middleware.auth import jwt_auth_mw` works.
"""

from __future__ import annotations

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

from auth.oidc import verify_jwt  # your existing verifier (RS256 / ES256 only)

_CLOCK_SKEW = 60  # seconds


async def jwt_auth_mw(request: Request, call_next):
    """
    • Extracts the Bearer token from the `Authorization` header.  
    • Verifies it with `auth.oidc.verify_jwt`.  
    • Stores the `sub` claim in `request.state.sub` for downstream middleware.  
    • Rejects the request with 401 on any failure.
    """
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"detail": "Missing Bearer token"})

    token = auth_header.split(" ", 1)[1]

    try:
        claims = verify_jwt(token, leeway=_CLOCK_SKEW)
    except Exception as exc: 
        return JSONResponse(status_code=401, content={"detail": str(exc)})
    

    # attach the user id (sub) for the session-middleware
    request.state.sub = claims["sub"]

    # continue down the middleware stack / route handler
    return await call_next(request)