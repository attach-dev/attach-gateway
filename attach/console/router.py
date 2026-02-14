"""
FastAPI router for console UI.

Routes:
  GET /console              - Serve console HTML (unauthenticated)
  GET /console/static/*     - Serve static assets (unauthenticated)
  GET /console/api/overview - Overview stats (JWT protected)
  GET /console/api/events   - Recent events (JWT protected)
  GET /console/api/servers  - Server list (JWT protected)

Security:
  - /console and /console/static/* are unauthenticated (no sensitive data)
  - /console/api/* requires JWT Bearer token
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

from attach.audit.sqlite import overview_stats, query_mcp_events
from attach.mcp.config import get_enabled_servers

log = logging.getLogger(__name__)

router = APIRouter(prefix="/console", tags=["console"])

# Path to console static files
STATIC_DIR = Path(__file__).parent / "static"


@router.get("")
async def serve_console():
    """Serve console HTML page (unauthenticated)."""
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        return JSONResponse(status_code=404, content={"detail": "Console UI not found"})
    return FileResponse(index_path, media_type="text/html")


@router.get("/static/{filename}")
async def serve_static(filename: str):
    """Serve static assets (unauthenticated)."""
    # Security: only allow specific file extensions
    allowed_extensions = {".js", ".css", ".html", ".png", ".svg", ".ico"}
    file_path = STATIC_DIR / filename

    if not file_path.exists() or file_path.suffix not in allowed_extensions:
        return JSONResponse(status_code=404, content={"detail": "File not found"})

    # Prevent directory traversal
    if not str(file_path.resolve()).startswith(str(STATIC_DIR.resolve())):
        return JSONResponse(status_code=403, content={"detail": "Access denied"})

    return FileResponse(file_path)


@router.get("/api/overview")
async def get_overview(request: Request):
    """
    Get overview statistics for dashboard (JWT protected).

    Returns:
      {
        "calls_today": int,
        "denies_today": int,
        "top_tools": [[tool, count], ...],
        "top_users": [[user, count], ...]
      }
    """
    # Auth middleware ensures request.state.sub exists
    stats = overview_stats()
    return stats


@router.get("/api/events")
async def get_events(
    request: Request,
    limit: int = 200,
    user: Optional[str] = None,
    server: Optional[str] = None,
):
    """
    Get recent MCP events (JWT protected).

    Query params:
      - limit: Max number of events (default 200)
      - user: Filter by user (optional)
      - server: Filter by server (optional)

    Returns:
      {
        "events": [...]
      }
    """
    # Auth middleware ensures request.state.sub exists
    events = query_mcp_events(limit=limit, user=user, server=server)
    return {"events": events}


@router.get("/api/servers")
async def get_servers(request: Request):
    """
    Get list of MCP servers (JWT protected).

    Returns:
      {
        "servers": {
          "server_name": {
            "enabled": true,
            "url": "http://..."
          }
        }
      }
    """
    # Auth middleware ensures request.state.sub exists
    enabled = get_enabled_servers()

    # Return sanitized view (no headers)
    servers = {}
    for name, config in enabled.items():
        servers[name] = {
            "enabled": config.get("enabled", False),
            "url": config.get("url", ""),
        }

    return {"servers": servers}
