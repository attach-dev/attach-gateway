from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from fastapi.responses import JSONResponse

router = APIRouter()

# --------------------------------------------------------------------------- #
# In-memory task table                                                        #
# --------------------------------------------------------------------------- #
# {task_id: {"state": str, "result": Any | None, "created": float}}
_TASKS: dict[str, dict[str, Any]] = {}
_LOCK = asyncio.Lock()             # cheap protection for concurrent writers
_TTL = 3600                        # seconds before we evict old tasks


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


async def _forward_call(body: dict[str, Any], headers: dict[str, str], task_id: str) -> None:
    """
    Fire-and-forget helper that forwards the wrapped `input` to the chat engine
    and stores the result (or error) in `_TASKS[task_id]`.
    """
    target = body.get("target_url") or "http://127.0.0.1:8080/api/chat"

    async with _LOCK:
        _TASKS[task_id]["state"] = "in_progress"

    try:
        async with httpx.AsyncClient(timeout=60) as cli:
            resp = await cli.post(target, json=body["input"], headers=headers)
        result: Any = resp.json()
        state = "done"
    except Exception as exc:       # noqa: BLE001 – surfacing any network/json error
        result = {"detail": str(exc)}
        state = "error"

    async with _LOCK:
        _TASKS[task_id].update(state=state, result=result)


async def _evict_expired() -> None:
    """Remove tasks older than _TTL seconds to keep memory bounded."""
    now = time.time()
    async with _LOCK:
        for tid in list(_TASKS.keys()):
            if now - _TASKS[tid]["created"] > _TTL:
                _TASKS.pop(tid, None)


# --------------------------------------------------------------------------- #
# Routes                                                                      #
# --------------------------------------------------------------------------- #
@router.post("/tasks/send")
async def tasks_send(req: Request, bg: BackgroundTasks):
    body = await req.json()
    if "input" not in body:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="payload must contain an 'input' field",
        )

    task_id = _new_id()
    async with _LOCK:
        _TASKS[task_id] = {"state": "queued", "result": None, "created": time.time()}

    # Forward only non-None headers; JWT is mandatory, session optional
    base_headers = {
        "Authorization": req.headers.get("authorization"),
        "X-UMP-Session": req.headers.get("x-ump-session"),
    }
    headers = {k: v for k, v in base_headers.items() if v is not None}

    bg.add_task(_forward_call, body, headers, task_id)
    bg.add_task(_evict_expired)

    return {"task_id": task_id, "state": "queued"}


@router.get("/tasks/status/{task_id}")
async def tasks_status(task_id: str):
    task = _TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="unknown task")
    return JSONResponse(task)