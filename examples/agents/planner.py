# examples/agents/planner.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
import os

app = FastAPI(title="Planner Agent")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")


class ChatRequest(BaseModel):
    model: str
    messages: list
    stream: bool = False


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """
    Proxy the incoming conversation to the local Ollama server (or any
    OpenAI‑compatible endpoint) and return its response verbatim so the
    gateway UI receives real model output instead of the previous stub.
    """
    payload = {
        "model": req.model,
        "messages": req.messages,
        # Ollama ignores 'stream' but forward it to stay compatible
        "stream": req.stream,
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(OLLAMA_URL, json=payload)
            resp.raise_for_status()
    except httpx.HTTPError as e:
        # surface a clean 502 for gateway diagnostics
        raise HTTPException(status_code=502, detail=f"Ollama request failed: {e}")

    return resp.json()