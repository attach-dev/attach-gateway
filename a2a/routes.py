from __future__ import annotations

import asyncio
import os
import time
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from fastapi.responses import JSONResponse

from mem import write as mem_write

router = APIRouter()

# --------------------------------------------------------------------------- #
# In-memory task table                                                        #
# --------------------------------------------------------------------------- #
# {task_id: {"state": str, "result": Any | None, "created": float}}
_TASKS: dict[str, dict[str, Any]] = {}
_LOCK = asyncio.Lock()  # cheap protection for concurrent writers
_TTL = 3600  # seconds before we evict old tasks


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


async def _execute_temporal(target: str, payload: dict[str, Any], task_id: str) -> Any:
    try:
        from temporalio.client import Client
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError("temporalio not installed") from exc

    workflow = target.removeprefix("temporal://")
    url = os.getenv("TEMPORAL_URL", "localhost:7233")
    client = await Client.connect(url)
    result = await client.execute_workflow(
        workflow,
        payload.get("messages", []),
        id=task_id,
        task_queue=os.getenv("TEMPORAL_QUEUE", "attach-gateway"),
    )
    return result


async def _forward_call(
    body: dict[str, Any],
    headers: dict[str, str],
    task_id: str,
    sid: str,
    sub: str,
) -> None:
    """
    Fire-and-forget helper that forwards the wrapped `input` to the chat engine
    and stores the result (or error) in `_TASKS[task_id]`.
    """
    target = body.get("target_url") or "http://127.0.0.1:8080/api/chat"

    async with _LOCK:
        _TASKS[task_id]["state"] = "in_progress"

    await mem_write(
        {
            "timestamp": time.time(),
            "session_id": sid,
            "user": sub,
            "task_id": task_id,
            "event": "task_sent",
            "payload": body.get("input"),
        }
    )

    try:
        if target.startswith("temporal://"):
            result = await _execute_temporal(target, body["input"], task_id)
            state = "done"
        else:
            async with httpx.AsyncClient(timeout=60) as cli:
                resp = await cli.post(target, json=body["input"], headers=headers)
            result = resp.json()
            state = "done"
    except Exception as exc:  # noqa: BLE001 – surfacing any network/json error
        result = {"detail": str(exc)}
        state = "error"

    async with _LOCK:
        _TASKS[task_id].update(state=state, result=result)

    await mem_write(
        {
            "timestamp": time.time(),
            "session_id": sid,
            "user": sub,
            "task_id": task_id,
            "event": "task_result",
            "state": state,
            "result": result,
        }
    )


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
        "X-Attach-Session": req.headers.get("x-attach-session"),
    }
    headers = {k: v for k, v in base_headers.items() if v is not None}

    sid = getattr(req.state, "sid", "") or req.headers.get("x-attach-session", "")
    sub = getattr(req.state, "sub", "")
    bg.add_task(
        _forward_call,
        body,
        headers,
        task_id,
        sid,
        sub,
    )
    bg.add_task(_evict_expired)

    return {"task_id": task_id, "state": "queued"}


@router.get("/tasks/status/{task_id}")
async def tasks_status(task_id: str):
    task = _TASKS.get(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="unknown task"
        )
    return JSONResponse(task)
