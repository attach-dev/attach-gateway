from __future__ import annotations

import time
from enum import Enum

from fastapi import APIRouter, BackgroundTasks, Response, status
from pydantic import BaseModel, Field

from mem.sakana import write as sakana_write

router = APIRouter()


class LogLevel(str, Enum):
    debug = "debug"
    info = "info"
    warn = "warn"
    error = "error"
    fatal = "fatal"


class SakanaLog(BaseModel):
    run_id: str
    level: LogLevel
    message: str
    timestamp: float = Field(default_factory=lambda: time.time())
    agent: str | None = None


@router.post("/v1/logs", status_code=status.HTTP_202_ACCEPTED)
async def ingest_log(event: SakanaLog, bg: BackgroundTasks) -> Response:
    bg.add_task(sakana_write, event.model_dump(mode="json"))
    return Response(status_code=status.HTTP_202_ACCEPTED)
