# middleware/session.py
from __future__ import annotations

import hashlib
import json
import time

from fastapi import Request, Response
from starlette.responses import JSONResponse

from mem import write as mem_write

# Paths that don't require authentication (same as auth middleware)
EXCLUDED_PATHS = {
    "/auth/config",
    "/docs",
    "/redoc",
    "/openapi.json",
}

def _session_id(sub: str, user_agent: str) -> str:
    return hashlib.sha256(f"{sub}:{user_agent}".encode()).hexdigest()


async def session_mw(request: Request, call_next):
    # Skip session middleware for excluded paths
    if request.url.path in EXCLUDED_PATHS:
        return await call_next(request)
    
    # Defensive guard – if sub is missing return 401 instead of 500
    if not hasattr(request.state, "sub"):
        return JSONResponse(status_code=401, content={"detail": "Unauthenticated"})

    sid = _session_id(request.state.sub, request.headers.get("user-agent", ""))
    request.state.sid = sid  # expose to downstream handlers

    response: Response = await call_next(request)
    response.headers["X-Attach-Session"] = sid[:16]  # expose *truncated* sid
    return response