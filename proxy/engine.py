from __future__ import annotations

import os
from typing import Any, AsyncIterator

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from starlette.responses import StreamingResponse

router = APIRouter()


async def _upstream_stream(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> AsyncIterator[bytes]:
    """
    Proxy the request to the chat engine and yield its bytes **as-they-arrive**.

    We keep memory usage constant by forwarding the async byte-stream instead of
    buffering the full response.
    """
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
            method,
            url,
            headers=headers,
            json=payload,
            timeout=None,
        ) as resp:
            # Propagate non-2xx as JSON later; for now just expose the body.
            async for chunk in resp.aiter_bytes():
                yield chunk


@router.post("/api/chat")
async def proxy_to_engine(request: Request):
    """
    Minimal pass-through to /v1/chat/completions on the configured ENGINE_URL.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Body must be valid JSON",
        )

    base = os.getenv("ENGINE_URL", "http://localhost:11434").rstrip("/")
    upstream_url = f"{base}/v1/chat/completions"

    # Pass along Bearer token if present
    headers: dict[str, str] = {}
    if auth := request.headers.get("Authorization"):
        headers["Authorization"] = auth

    try:
        return StreamingResponse(
            _upstream_stream(request.method, upstream_url, headers=headers, payload=body),
            media_type="application/json",
        )
    except httpx.HTTPStatusError as exc:
        # Bubble the upstream status so callers can act accordingly
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)
    except Exception as exc:
        # Log & hide internals from the client
        # (LOGGER omitted for brevity – add one if you like)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Upstream chat engine error",
        ) from exc