from __future__ import annotations

"""Factory for usage backends."""

import os
import warnings

from .backends import (
    AbstractUsageBackend,
    NullUsageBackend,
    OpenMeterBackend,
    PrometheusUsageBackend,
)


def _select_backend() -> str:
    """Return backend name from env vars with deprecation warning."""
    if "USAGE_METERING" in os.environ:
        return os.getenv("USAGE_METERING", "null")
    if "USAGE_BACKEND" in os.environ:
        warnings.warn(
            "USAGE_BACKEND is deprecated; rename to USAGE_METERING",
            UserWarning,
            stacklevel=2,
        )
    return os.getenv("USAGE_BACKEND", "null")


def get_usage_backend(kind: str) -> AbstractUsageBackend:
    """Return an instance of the requested usage backend."""
    kind = (kind or "null").lower()
    if kind == "prometheus":
        try:
            return PrometheusUsageBackend()
        except Exception:
            return NullUsageBackend()
    if kind == "openmeter":
        try:
            return OpenMeterBackend()
        except Exception:
            return NullUsageBackend()
    return NullUsageBackend()
