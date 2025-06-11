import asyncio
import os

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

os.environ["MEM_BACKEND"] = "none"

from a2a.routes import _TASKS
from a2a.routes import router as a2a_router


@pytest.mark.asyncio
async def test_tasks_send_logs_events(monkeypatch):
    events = []

    async def fake_write(event):
        events.append(event)

    async def fake_forward_call(body, headers, task_id, sid, sub):
        await fake_write({"event": "task_sent", "task_id": task_id})
        await fake_write({"event": "task_result", "task_id": task_id})

    monkeypatch.setattr("a2a.routes.mem_write", fake_write)
    monkeypatch.setattr("a2a.routes._forward_call", fake_forward_call)

    _TASKS.clear()

    app = FastAPI()
    app.include_router(a2a_router, prefix="/a2a")

    headers = {"Authorization": "Bearer t", "X-Attach-Session": "sid"}
    body = {"input": {"messages": [{"content": "hi"}]}}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/a2a/tasks/send", json=body, headers=headers)
        tid = resp.json()["task_id"]
        await asyncio.sleep(0.05)

    assert len(events) == 2
    assert events[0]["event"] == "task_sent"
    assert events[1]["event"] == "task_result"
    assert all(e["task_id"] == tid for e in events)
