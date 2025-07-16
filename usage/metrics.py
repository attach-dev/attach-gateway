from __future__ import annotations

"""Utilities for exposing Attach Gateway usage metrics."""

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, Response


def mount_metrics(app: FastAPI) -> None:
    """Attach a Prometheus-compatible ``/metrics`` route to ``app``."""

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:  # noqa: D401
        usage = getattr(app.state, "usage", None)
        if usage is None:
            return PlainTextResponse("# No usage backend configured\n")
        try:
            from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest
        except ImportError:
            counter = getattr(usage, "counter", None)
            if counter is None or not hasattr(counter, "values"):
                return PlainTextResponse("# No metrics available\n")
            lines = [
                "# HELP attach_usage_tokens_total Total tokens processed by Attach Gateway",
                "# TYPE attach_usage_tokens_total counter",
            ]
            for (u, d, m), v in counter.values.items():
                lines.append(
                    f'attach_usage_tokens_total{{user="{u}",direction="{d}",model="{m}"}} {v}'
                )
            return PlainTextResponse("\n".join(lines) + "\n")
        else:
            if not hasattr(usage, "counter"):
                return PlainTextResponse("# No usage counter\n")
            return PlainTextResponse(
                generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST
            )
