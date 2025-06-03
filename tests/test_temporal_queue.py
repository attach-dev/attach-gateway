import asyncio

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from a2a.routes import _TASKS
from a2a.routes import router as a2a_router

pytest.importorskip("temporalio")


@pytest.mark.asyncio
async def test_temporal_scheme_triggers_workflow(monkeypatch):
    async def fake_execute(target, payload, task_id):
        assert target == "temporal://ProcessChat"
        return "Processed 2 tokens"

    monkeypatch.setattr("a2a.routes._execute_temporal", fake_execute)

    app = FastAPI()
    app.include_router(a2a_router, prefix="/a2a")

    headers = {"Authorization": "Bearer t"}
    body = {
        "input": {"messages": [{"content": "hi"}]},
        "target_url": "temporal://ProcessChat",
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/a2a/tasks/send", json=body, headers=headers)
        tid = resp.json()["task_id"]
        await asyncio.sleep(0.1)
        status_resp = await client.get(f"/a2a/tasks/status/{tid}", headers=headers)

    assert status_resp.json()["result"] == "Processed 2 tokens"
