from __future__ import annotations
"""
LangGraph → Attach-Gateway demo
────────────────────────────
Queues an Ollama chat via /a2a/tasks/send, polls the status endpoint, and
prints the assistant reply.
Prerequisites
  $ export JWT=$(cat token.txt)           # bearer token
  $ uvicorn main:app --port 8080          # gateway running
  $ pip install langgraph>=0.0.48 langchain-core>=0.3.0 httpx
"""
import asyncio, hashlib, json, os, time
from typing import List, TypedDict

import httpx
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import StateGraph, END

# ───────────────────────── Config ──────────────────────────
JWT    = os.environ["JWT"]
GW_URL = os.getenv("GW_URL", "http://127.0.0.1:8080")
SID    = hashlib.sha256((JWT + "demo").encode()).hexdigest()[:16]

HEADERS             = {"Authorization": f"Bearer {JWT}"}
HEADERS_WITH_SESSION = HEADERS | {"X-Attach-Session": SID}

# ─────────────── Helpers: queue + poll Ollama ──────────────
def lc_to_openai(msg: BaseMessage) -> dict:
    role_map = {"human": "user", "ai": "assistant"}
    return {"role": role_map.get(msg.type, msg.type), "content": msg.content}

async def queue_chat(payload: dict) -> str:
    async with httpx.AsyncClient() as cli:
        r = await cli.post(
            f"{GW_URL}/a2a/tasks/send",
            json={"input": payload},
            headers=HEADERS_WITH_SESSION,
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["task_id"]

async def wait_for_result(tid: str, every: float = 0.5) -> dict:
    async with httpx.AsyncClient() as cli:
        while True:
            r = await cli.get(
                f"{GW_URL}/a2a/tasks/status/{tid}",
                headers=HEADERS, timeout=10
            )
            j = r.json()
            if j["state"] in {"done", "error"}:
                return j
            await asyncio.sleep(every)

async def ask_ollama(msgs: List[BaseMessage]) -> str:
    tid = await queue_chat({
        "model": "tinyllama",
        "messages": [lc_to_openai(m) for m in msgs],
        "stream": False,
    })
    res = await wait_for_result(tid)
    if res["state"] == "error":
        raise RuntimeError(res["result"])
    return res["result"]["choices"][0]["message"]["content"]

# ─────────────── LangGraph definition ──────────────────────
class State(TypedDict):
    messages: List[BaseMessage]
    reply: str | None

async def planner(state: State) -> State:
    if any(kw in state["messages"][-1].content.lower() for kw in ("code", "python")):
        state["reply"] = await ask_ollama(state["messages"])
    else:
        state["reply"] = "No code requested."
    return state

sg = StateGraph(State)
sg.add_node("planner", planner)
sg.set_entry_point("planner")
sg.add_edge("planner", END)
graph = sg.compile()

# ───────────────────────── Runner ──────────────────────────
async def main() -> None:
    prompt = "Write python to sort a list"
    init: State = {"messages": [HumanMessage(content=prompt)], "reply": None}

    t0 = time.perf_counter()
    final: State = await graph.ainvoke(init)
    print(f"\nAssistant reply (took {time.perf_counter() - t0:.2f}s):\n")
    print(json.dumps(final["reply"], indent=2))

if __name__ == "__main__":
    asyncio.run(main())