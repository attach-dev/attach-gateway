"""Env helpers used across entry-points."""

import logging
import os

log = logging.getLogger(__name__)


def int_env(var: str, default: int | None = None) -> int | None:
    """Read $VAR as positive int.
    • '', 'null', 'none', 'false', 'infinite'  -> None
    • invalid / non-positive -> default
    """
    val = os.getenv(var)
    if val is None:
        return default
    val = val.strip().lower()
    if val in {"", "null", "none", "false", "infinite"}:
        return None
    try:
        num = int(val)
        return num if num > 0 else default
    except ValueError:
        log.warning("⚠️  %s=%s is not a valid int; using default=%s", var, val, default)
        return default
