from __future__ import annotations

"""Expose gateway metrics."""

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/v1/metrics")
async def metrics(request: Request) -> dict[str, int]:
    """Return cached metrics from Redis if available."""

    cache = getattr(request.app.state, "cache", None)
    client = getattr(cache, "_client", None)
    if client is None:
        return {"cache_hits": 0, "jobs_processed": 0}
    try:
        hits = int(client.get("metrics:cache_hits") or 0)
        jobs = int(client.get("metrics:jobs_processed") or 0)
    except Exception:
        hits = jobs = 0
    return {"cache_hits": hits, "jobs_processed": jobs}
