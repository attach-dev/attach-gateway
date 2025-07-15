from __future__ import annotations

"""Factory for usage backends."""

from .backends import (
    AbstractUsageBackend,
    NullUsageBackend,
    OpenMeterBackend,
    PrometheusUsageBackend,
)


def get_usage_backend(kind: str) -> AbstractUsageBackend:
    """Return an instance of the requested usage backend."""
    kind = (kind or "null").lower()
    if kind == "prometheus":
        try:
            return PrometheusUsageBackend()
        except Exception:
            return NullUsageBackend()
    if kind == "openmeter":
        return OpenMeterBackend()
    return NullUsageBackend()
