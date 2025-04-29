# middleware/session.py
from __future__ import annotations
import hashlib, time, json
from mem import write as mem_write
from fastapi import Request, Response
from starlette.responses import JSONResponse

def _session_id(sub: str, user_agent: str) -> str:
    return hashlib.sha256(f"{sub}:{user_agent}".encode()).hexdigest()

async def session_mw(request: Request, call_next):
    # Defensive guard – if sub is missing return 401 instead of 500
    if not hasattr(request.state, "sub"):
        return JSONResponse(status_code=401, content={"detail": "Unauthenticated"})

    sid = _session_id(request.state.sub, request.headers.get("user-agent", ""))
    request.state.sid = sid             # expose to downstream handlers

    response: Response = await call_next(request)
    response.headers["X-UMP-Session-Id"] = sid[:16]  # expose *truncated* sid
    return response
