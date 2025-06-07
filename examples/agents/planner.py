# examples/agents/planner.py
from fastapi import FastAPI
from pydantic import BaseModel
import time, uuid

app = FastAPI(title="Planner Agent")

class ChatRequest(BaseModel):
    model: str
    messages: list
    stream: bool = False

@app.post("/api/chat")
async def chat(req: ChatRequest):
    user_msg = req.messages[-1]["content"]
    plan = (
        "### Plan\n"
        f"1. Understand: “{user_msg}”\n"
        "2. Decide which functions we need\n"
        "3. Hand off to coder with a short spec"
    )

    return {
        "id": f"plan-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "planner",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": plan},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": len(plan.split()), "total_tokens": 0},
    }