"""
FastAPI router for MCP gateway endpoints.

Routes:
  GET  /mcp         - List enabled MCP servers
  POST /mcp/{name}  - Proxy JSON-RPC request to named server
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from mcp.config import get_enabled_servers
from mcp.proxy import proxy_mcp_request

log = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp"])


@router.get("")
async def list_mcp_servers():
    """
    List all enabled MCP servers.

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
    enabled = get_enabled_servers()

    # Return sanitized view (no headers)
    servers = {}
    for name, config in enabled.items():
        servers[name] = {
            "enabled": config.get("enabled", False),
            "url": config.get("url", ""),
        }

    return {"servers": servers}


@router.post("/{server}")
async def proxy_to_mcp_server(server: str, request: Request):
    """
    Proxy a JSON-RPC request to the named MCP server.

    Args:
        server: Server name from URL path
        request: FastAPI request containing JSON-RPC body

    Returns:
        JSON-RPC response from upstream server

    Notes:
        - Requires Bearer token authentication (JWT)
        - Enforces quota for tools/call method
        - Logs all requests to audit log
    """
    # Extract user from request.state (set by auth middleware)
    user = getattr(request.state, "sub", "unknown")

    # Parse JSON body
    try:
        body: dict[str, Any] = await request.json()
    except Exception as exc:
        log.warning("Failed to parse JSON-RPC body: %s", exc)
        return JSONResponse(
            status_code=400,
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error: invalid JSON"},
            },
        )

    # Proxy the request
    status_code, response_body = await proxy_mcp_request(server, body, user)

    return JSONResponse(status_code=status_code, content=response_body)
