# examples/agents/coder.py   (drop this in as a full replacement)
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx, os, time, uuid
from typing import List, Dict, Any

ENGINE_URL = os.getenv("ENGINE_URL", "http://127.0.0.1:11434")
app        = FastAPI(title="Coder Agent")

class ChatRequest(BaseModel):
    model: str
    messages: List[Dict[str, Any]]
    stream:  bool = False


def _fmt_error(text: str) -> Dict[str, Any]:
    """
    Wrap a raw error string from the engine so the front-end
    can still render it as a normal chat bubble.
    """
    return {
        "id": f"err-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model":   "coder-error",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": f"⚠️ Engine error:\n\n```text\n{text.strip()}\n```",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


@app.post("/api/chat")
async def chat(req: ChatRequest):
    prompt = req.messages[-1]["content"]

    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            f"{ENGINE_URL}/api/chat",
            json={
                "model": req.model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a helpful coding assistant. "
                            "Reply with concise, runnable code when possible."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
            },
        )

    # ── 1) Non-200 HTTP status ───────────────────────────────
    if r.status_code != 200:
        raise HTTPException(502, f"Engine HTTP {r.status_code}: {r.text[:120]}")

    # ── 2) Try to parse JSON; fall back to plain text ────────
    payload: Dict[str, Any]
    try:
        payload = r.json()
    except ValueError:
        # Plain-text or HTML error; surface it as a normal answer
        return _fmt_error(r.text)

    # ── 3) Engine returned {"error": "..."} structure ─────────
    if isinstance(payload, dict) and payload.get("error"):
        return _fmt_error(payload["error"])

    # ── 4) Happy path – validate minimal structure ───────────
    if ("choices" not in payload) or not payload["choices"]:
        return _fmt_error(f"Invalid engine payload: {payload!r}")

    return payload