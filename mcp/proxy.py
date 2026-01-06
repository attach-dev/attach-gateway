"""
MCP reverse proxy logic.

Forwards JSON-RPC requests to configured MCP servers.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

import httpx

from audit.sqlite import insert_mcp_event
from mcp.config import get_enabled_servers, get_server_headers
from mcp.quota import check_quota, record_tool_call

log = logging.getLogger(__name__)

# Default timeout for MCP upstream requests (seconds)
DEFAULT_TIMEOUT = 30.0


def get_mcp_timeout() -> float:
    """Get MCP proxy timeout from environment."""
    timeout_str = os.getenv("ATTACH_MCP_TIMEOUT", str(DEFAULT_TIMEOUT))
    try:
        return float(timeout_str)
    except ValueError:
        log.warning(
            "Invalid ATTACH_MCP_TIMEOUT=%s, using default %s",
            timeout_str,
            DEFAULT_TIMEOUT,
        )
        return DEFAULT_TIMEOUT


def extract_tool_name(body: dict[str, Any]) -> Optional[str]:
    """
    Extract tool name from JSON-RPC tools/call request.

    Expected structure:
      {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
          "name": "github.create_issue",
          ...
        },
        "id": 1
      }
    """
    if body.get("method") != "tools/call":
        return None

    params = body.get("params", {})
    if isinstance(params, dict):
        return params.get("name")

    return None


async def proxy_mcp_request(
    server_name: str,
    body: dict[str, Any],
    user: str,
) -> tuple[int, dict[str, Any]]:
    """
    Proxy a JSON-RPC request to the configured MCP server.

    Args:
        server_name: Name of the MCP server
        body: JSON-RPC request body
        user: User identifier (from JWT sub claim)

    Returns:
        (status_code, response_body)

    Notes:
        - Enforces quota if method is "tools/call"
        - Logs all requests to audit log
        - Does NOT forward client Authorization header
        - Uses configured headers from mcp.json
    """
    start_time = time.time()

    # Check if server exists and is enabled
    enabled_servers = get_enabled_servers()
    if server_name not in enabled_servers:
        insert_mcp_event(
            user=user,
            server=server_name,
            method=None,
            tool=None,
            allowed=False,
            error="server not found or disabled",
        )
        return (
            404,
            {
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "error": {
                    "code": -32001,
                    "message": f"MCP server '{server_name}' not found or disabled",
                },
            },
        )

    server_config = enabled_servers[server_name]
    upstream_url = server_config.get("url")
    if not upstream_url:
        insert_mcp_event(
            user=user,
            server=server_name,
            method=None,
            tool=None,
            allowed=False,
            error="server URL not configured",
        )
        return (
            500,
            {
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "error": {
                    "code": -32002,
                    "message": f"MCP server '{server_name}' has no URL configured",
                },
            },
        )

    # Extract method and tool name for quota enforcement
    method = body.get("method")
    tool = extract_tool_name(body) if method == "tools/call" else None

    # Quota check for tools/call
    if method == "tools/call" and tool:
        allowed, error_msg = check_quota(user, tool)
        if not allowed:
            latency_ms = (time.time() - start_time) * 1000
            insert_mcp_event(
                user=user,
                server=server_name,
                method=method,
                tool=tool,
                allowed=False,
                latency_ms=latency_ms,
                error=error_msg,
            )
            return (
                200,
                {
                    "jsonrpc": "2.0",
                    "id": body.get("id"),
                    "error": {
                        "code": -32029,
                        "message": "tool quota exceeded",
                        "data": {
                            "tool": tool,
                            "error": error_msg,
                        },
                    },
                },
            )

    # Forward request to upstream
    headers = get_server_headers(server_config)
    headers["Content-Type"] = "application/json"

    timeout = get_mcp_timeout()

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(upstream_url, json=body, headers=headers)

        latency_ms = (time.time() - start_time) * 1000

        # Record successful call
        if method == "tools/call" and tool:
            record_tool_call(user, tool)

        insert_mcp_event(
            user=user,
            server=server_name,
            method=method,
            tool=tool,
            allowed=True,
            latency_ms=latency_ms,
            error=None if response.is_success else f"HTTP {response.status_code}",
        )

        # Return upstream response
        try:
            response_json = response.json()
        except Exception:
            response_json = {"error": "upstream returned non-JSON response"}

        return (response.status_code, response_json)

    except httpx.TimeoutException:
        latency_ms = (time.time() - start_time) * 1000
        insert_mcp_event(
            user=user,
            server=server_name,
            method=method,
            tool=tool,
            allowed=False,
            latency_ms=latency_ms,
            error="upstream timeout",
        )
        return (
            504,
            {
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "error": {
                    "code": -32003,
                    "message": f"MCP server '{server_name}' timeout after {timeout}s",
                },
            },
        )

    except httpx.RequestError as exc:
        latency_ms = (time.time() - start_time) * 1000
        error_msg = f"upstream error: {exc}"
        insert_mcp_event(
            user=user,
            server=server_name,
            method=method,
            tool=tool,
            allowed=False,
            latency_ms=latency_ms,
            error=error_msg,
        )
        return (
            502,
            {
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "error": {
                    "code": -32004,
                    "message": f"Failed to reach MCP server '{server_name}'",
                    "data": str(exc),
                },
            },
        )
