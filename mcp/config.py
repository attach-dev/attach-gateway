"""
MCP server configuration loader.

Config file: ~/.attach/mcp.json

Schema:
{
  "version": 1,
  "servers": {
    "server_name": {
      "enabled": true,
      "url": "http://localhost:7001/mcp",
      "headers": {
        "Authorization": "env:NOTION_TOKEN",
        "X-Custom": "literal-value"
      }
    }
  }
}
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)


def _attach_dir_path() -> Path:
    """Return ~/.attach directory path (does NOT create it)."""
    return Path.home() / ".attach"


def get_attach_dir() -> Path:
    """Return ~/.attach directory, creating if needed."""
    attach_dir = _attach_dir_path()
    attach_dir.mkdir(exist_ok=True)
    return attach_dir


def get_mcp_config_path() -> Path:
    """Return path to MCP config file (does NOT create ~/.attach)."""
    return _attach_dir_path() / "mcp.json"


def load_mcp_config() -> dict[str, Any]:
    """
    Load MCP configuration from ~/.attach/mcp.json.
    Returns empty config structure if file doesn't exist.
    """
    path = get_mcp_config_path()
    if not path.exists():
        return {"version": 1, "servers": {}}

    try:
        with open(path, "r", encoding="utf-8") as f:
            config = json.load(f)
        return config
    except (json.JSONDecodeError, IOError) as exc:
        log.warning("Failed to load MCP config from %s: %s", path, exc)
        return {"version": 1, "servers": {}}


def save_mcp_config(config: dict[str, Any]) -> None:
    """Save MCP configuration to ~/.attach/mcp.json."""
    path = get_mcp_config_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except IOError as exc:
        log.error("Failed to save MCP config to %s: %s", path, exc)
        raise


def get_enabled_servers() -> dict[str, dict[str, Any]]:
    """Return dict of enabled MCP servers with their configs."""
    config = load_mcp_config()
    servers = config.get("servers", {})
    return {
        name: server_config
        for name, server_config in servers.items()
        if server_config.get("enabled", False)
    }


def resolve_header_value(value: str) -> str:
    """
    Resolve header value, supporting env: prefix for environment variables.

    Examples:
      "Bearer token123" -> "Bearer token123"
      "env:NOTION_TOKEN" -> os.getenv("NOTION_TOKEN", "")
    """
    if value.startswith("env:"):
        var_name = value[4:]
        resolved = os.getenv(var_name, "")
        if not resolved:
            log.warning("Environment variable %s not set for MCP header", var_name)
        return resolved
    return value


def get_server_headers(server_config: dict[str, Any]) -> dict[str, str]:
    """
    Extract and resolve headers for a server configuration.
    Never logs resolved secrets.
    """
    headers_config = server_config.get("headers", {})
    resolved = {}
    for key, value in headers_config.items():
        resolved_value = resolve_header_value(value)
        if resolved_value:
            resolved[key] = resolved_value
    return resolved


def is_mcp_enabled() -> bool:
    """
    Check if MCP gateway is enabled.
    Returns True if ATTACH_ENABLE_MCP=true OR if ~/.attach/mcp.json exists.

    Note: This function does NOT create ~/.attach directory as a side effect.
    """
    if os.getenv("ATTACH_ENABLE_MCP", "").lower() == "true":
        return True
    # Use get_mcp_config_path() which doesn't create the directory
    return get_mcp_config_path().exists()
