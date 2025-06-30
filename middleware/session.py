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
    
    # Let the auth middleware handle authentication first
    response: Response = await call_next(request)
    
    # Only set session ID if sub is available (after auth middleware runs)
    if hasattr(request.state, "sub"):
        sid = _session_id(request.state.sub, request.headers.get("user-agent", ""))
        request.state.sid = sid  # expose to downstream handlers
        response.headers["X-Attach-Session"] = sid[:16]  # expose *truncated* sid
        response.headers["X-Attach-User"]    = request.state.sub[:32]
    return response