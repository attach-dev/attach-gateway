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

from audit.sqlite import atomic_increment_and_get_quota_count, increment_quota_count
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
    2. First glob pattern that matches (excluding bare "*")
    3. Wildcard "*" if present (catch-all fallback)
    """
    policy = load_policy()
    limits = policy.get("per_user_daily_tool_calls", {})

    # Exact match first
    if tool in limits:
        return limits[tool]

    # Try glob patterns (skip bare "*" - it's handled as fallback)
    for pattern, limit in limits.items():
        # Skip the bare "*" pattern - we apply it only as final fallback
        if pattern == "*":
            continue
        if "*" in pattern or "?" in pattern or "[" in pattern:
            if fnmatch.fnmatch(tool, pattern):
                return limit

    # Fallback to wildcard catch-all (only if no specific pattern matched)
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

    NOTE: This only checks the quota without incrementing. Use check_and_reserve_quota()
    for atomic check-and-increment to prevent TOCTOU race conditions.

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
    # Use atomic increment to get current count and reserve our slot
    new_count = atomic_increment_and_get_quota_count(user, tool, date_utc)

    # new_count is the count AFTER increment (1-based)
    # So if limit=1, we allow new_count=1 but deny new_count=2
    if new_count > limit:
        error_msg = f"tool quota exceeded: {tool} limit={limit} used={new_count}"
        return (False, error_msg)

    return (True, None)


def record_tool_call(user: str, tool: str) -> None:
    """
    Record a tool call in quota counters.

    NOTE: This is now a no-op when quota is enabled because check_quota()
    atomically increments the counter. Kept for backwards compatibility
    and for cases where quota is disabled but tracking is still desired.
    """
    if not is_quota_enabled():
        # Only increment if quota is disabled (for tracking without enforcement)
        return

    # When quota is enabled, the counter was already incremented in check_quota()
    # No need to increment again
    pass
