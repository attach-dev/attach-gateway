"""
MCP tool call quota enforcement.

Policy file: ~/.attach/mcp_policy.json

Schema:
{
  "version": 1,
  "enabled": true,
  "per_user_daily_tool_calls": {
    "github.*": 200,
    "notion.*": 100,
    "*": 1000
  }
}

Quota enforcement:
- Only applies when method == "tools/call"
- Uses fnmatch glob patterns for tool names
- Day boundary: UTC midnight
- Counters stored in SQLite (audit/sqlite.py)
"""

from __future__ import annotations

import fnmatch
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from audit.sqlite import get_quota_count, increment_quota_count
from mcp.config import get_attach_dir

log = logging.getLogger(__name__)


def get_policy_path() -> Path:
    """Return path to MCP policy file."""
    return get_attach_dir() / "mcp_policy.json"


def load_policy() -> dict[str, Any]:
    """Load MCP quota policy from ~/.attach/mcp_policy.json."""
    path = get_policy_path()
    if not path.exists():
        return {"version": 1, "enabled": False, "per_user_daily_tool_calls": {}}

    try:
        with open(path, "r", encoding="utf-8") as f:
            policy = json.load(f)
        return policy
    except (json.JSONDecodeError, IOError) as exc:
        log.warning("Failed to load MCP policy from %s: %s", path, exc)
        return {"version": 1, "enabled": False, "per_user_daily_tool_calls": {}}


def is_quota_enabled() -> bool:
    """Check if quota enforcement is enabled."""
    policy = load_policy()
    return policy.get("enabled", False)


def get_tool_limit(tool: str) -> Optional[int]:
    """
    Get daily tool call limit for a given tool name using glob matching.
    Returns None if no limit applies.

    Matching priority:
    1. Exact match
    2. First glob pattern that matches
    3. Wildcard "*" if present
    """
    policy = load_policy()
    limits = policy.get("per_user_daily_tool_calls", {})

    # Exact match first
    if tool in limits:
        return limits[tool]

    # Try glob patterns
    for pattern, limit in limits.items():
        if "*" in pattern or "?" in pattern or "[" in pattern:
            if fnmatch.fnmatch(tool, pattern):
                return limit

    # Fallback to wildcard
    if "*" in limits:
        return limits["*"]

    return None


def get_current_date_utc() -> str:
    """Return current date in UTC as YYYY-MM-DD string."""
    now_utc = datetime.now(timezone.utc)
    return now_utc.strftime("%Y-%m-%d")


def check_quota(user: str, tool: str) -> tuple[bool, Optional[str]]:
    """
    Check if user is within quota for tool.

    Returns:
        (allowed: bool, error_msg: Optional[str])
        - (True, None) if allowed
        - (False, "quota exceeded...") if denied
    """
    if not is_quota_enabled():
        return (True, None)

    limit = get_tool_limit(tool)
    if limit is None:
        # No limit configured for this tool
        return (True, None)

    date_utc = get_current_date_utc()
    current_count = get_quota_count(user, tool, date_utc)

    if current_count >= limit:
        error_msg = f"tool quota exceeded: {tool} limit={limit} used={current_count}"
        return (False, error_msg)

    return (True, None)


def record_tool_call(user: str, tool: str) -> None:
    """Record a tool call in quota counters."""
    if not is_quota_enabled():
        return

    date_utc = get_current_date_utc()
    increment_quota_count(user, tool, date_utc)
