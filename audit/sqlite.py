"""
SQLite-based audit log for MCP events.

Database: ~/.attach/attach.db

Schema:
  mcp_events(
    id INTEGER PRIMARY KEY,
    ts REAL,
    user TEXT,
    server TEXT,
    method TEXT,
    tool TEXT,
    allowed INTEGER,
    latency_ms REAL,
    error TEXT
  )

  mcp_counters(
    date_utc TEXT,
    user TEXT,
    tool TEXT,
    count INTEGER,
    PRIMARY KEY(date_utc, user, tool)
  )
"""

from __future__ import annotations

import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from mcp.config import get_attach_dir

log = logging.getLogger(__name__)


def get_db_path() -> Path:
    """Return path to audit database."""
    return get_attach_dir() / "attach.db"


def init_db() -> None:
    """Initialize audit database schema."""
    db_path = get_db_path()
    conn = sqlite3.connect(db_path, timeout=5.0)
    try:
        cursor = conn.cursor()

        # Enable WAL mode for better concurrency
        cursor.execute("PRAGMA journal_mode=WAL;")

        # MCP events table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS mcp_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                user TEXT NOT NULL,
                server TEXT NOT NULL,
                method TEXT,
                tool TEXT,
                allowed INTEGER NOT NULL,
                latency_ms REAL,
                error TEXT
            )
        """
        )

        # Index for queries
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_mcp_events_ts
            ON mcp_events(ts DESC)
        """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_mcp_events_user
            ON mcp_events(user)
        """
        )

        # MCP quota counters table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS mcp_counters (
                date_utc TEXT NOT NULL,
                user TEXT NOT NULL,
                tool TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(date_utc, user, tool)
            )
        """
        )

        conn.commit()
    finally:
        conn.close()


def insert_mcp_event(
    user: str,
    server: str,
    method: Optional[str],
    tool: Optional[str],
    allowed: bool,
    latency_ms: Optional[float] = None,
    error: Optional[str] = None,
) -> None:
    """Insert an MCP event into audit log."""
    db_path = get_db_path()
    try:
        conn = sqlite3.connect(db_path, timeout=5.0)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO mcp_events (ts, user, server, method, tool, allowed, latency_ms, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    time.time(),
                    user,
                    server,
                    method,
                    tool,
                    int(allowed),
                    latency_ms,
                    error,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        log.error("Failed to insert MCP event: %s", exc)


def query_mcp_events(
    limit: int = 200,
    user: Optional[str] = None,
    server: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Query MCP events from audit log."""
    db_path = get_db_path()
    if not db_path.exists():
        return []

    try:
        conn = sqlite3.connect(db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()

            query = "SELECT * FROM mcp_events WHERE 1=1"
            params: list[Any] = []

            if user:
                query += " AND user = ?"
                params.append(user)
            if server:
                query += " AND server = ?"
                params.append(server)

            query += " ORDER BY ts DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            return [dict(row) for row in rows]
        finally:
            conn.close()
    except sqlite3.Error as exc:
        log.error("Failed to query MCP events: %s", exc)
        return []


def overview_stats() -> dict[str, Any]:
    """
    Return overview statistics for console dashboard.

    Returns:
      {
        "calls_today": int,
        "denies_today": int,
        "top_tools": [(tool, count), ...],
        "top_users": [(user, count), ...]
      }
    """
    db_path = get_db_path()
    if not db_path.exists():
        return {
            "calls_today": 0,
            "denies_today": 0,
            "top_tools": [],
            "top_users": [],
        }

    try:
        conn = sqlite3.connect(db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()

            # Calculate today's midnight UTC timestamp
            now_utc = datetime.now(timezone.utc)
            today_midnight = datetime(
                now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc
            )
            today_ts = today_midnight.timestamp()

            # Calls today
            cursor.execute(
                "SELECT COUNT(*) as cnt FROM mcp_events WHERE ts >= ?", (today_ts,)
            )
            calls_today = cursor.fetchone()["cnt"]

            # Denies today
            cursor.execute(
                "SELECT COUNT(*) as cnt FROM mcp_events WHERE ts >= ? AND allowed = 0",
                (today_ts,),
            )
            denies_today = cursor.fetchone()["cnt"]

            # Top tools (all time, limited to avoid huge results)
            cursor.execute(
                """
                SELECT tool, COUNT(*) as cnt
                FROM mcp_events
                WHERE tool IS NOT NULL
                GROUP BY tool
                ORDER BY cnt DESC
                LIMIT 10
            """
            )
            top_tools = [(row["tool"], row["cnt"]) for row in cursor.fetchall()]

            # Top users (all time)
            cursor.execute(
                """
                SELECT user, COUNT(*) as cnt
                FROM mcp_events
                GROUP BY user
                ORDER BY cnt DESC
                LIMIT 10
            """
            )
            top_users = [(row["user"], row["cnt"]) for row in cursor.fetchall()]

            return {
                "calls_today": calls_today,
                "denies_today": denies_today,
                "top_tools": top_tools,
                "top_users": top_users,
            }
        finally:
            conn.close()
    except sqlite3.Error as exc:
        log.error("Failed to compute overview stats: %s", exc)
        return {
            "calls_today": 0,
            "denies_today": 0,
            "top_tools": [],
            "top_users": [],
        }


def get_quota_count(user: str, tool: str, date_utc: str) -> int:
    """Get current quota count for a user/tool/day."""
    db_path = get_db_path()
    if not db_path.exists():
        return 0

    try:
        conn = sqlite3.connect(db_path, timeout=5.0)
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT count FROM mcp_counters WHERE date_utc = ? AND user = ? AND tool = ?",
                (date_utc, user, tool),
            )
            row = cursor.fetchone()
            return row[0] if row else 0
        finally:
            conn.close()
    except sqlite3.Error as exc:
        log.error("Failed to get quota count: %s", exc)
        return 0


def increment_quota_count(user: str, tool: str, date_utc: str) -> None:
    """Increment quota counter for a user/tool/day."""
    db_path = get_db_path()
    try:
        conn = sqlite3.connect(db_path, timeout=5.0)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO mcp_counters (date_utc, user, tool, count)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(date_utc, user, tool)
                DO UPDATE SET count = count + 1
                """,
                (date_utc, user, tool),
            )
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        log.error("Failed to increment quota count: %s", exc)


def atomic_increment_and_get_quota_count(user: str, tool: str, date_utc: str) -> int:
    """
    Atomically increment quota counter and return the NEW count.

    This prevents TOCTOU race conditions by incrementing first, then returning
    the new count so the caller can check if the limit was exceeded.

    Returns:
        The count AFTER increment (1-based). Returns 0 on error.
    """
    db_path = get_db_path()
    try:
        conn = sqlite3.connect(db_path, timeout=5.0)
        try:
            cursor = conn.cursor()
            # Use RETURNING clause to atomically increment and get new value
            # SQLite 3.35+ supports RETURNING
            cursor.execute(
                """
                INSERT INTO mcp_counters (date_utc, user, tool, count)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(date_utc, user, tool)
                DO UPDATE SET count = count + 1
                RETURNING count
                """,
                (date_utc, user, tool),
            )
            row = cursor.fetchone()
            conn.commit()
            return row[0] if row else 1
        finally:
            conn.close()
    except sqlite3.Error as exc:
        log.error("Failed to atomic increment quota count: %s", exc)
        # On error, return 0 (allow the request - fail open)
        return 0
