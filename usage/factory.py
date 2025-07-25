from __future__ import annotations

"""Factory for usage backends."""

import os
import warnings
import logging

from .backends import (
    AbstractUsageBackend,
    NullUsageBackend,
    OpenMeterBackend,
    PrometheusUsageBackend,
)

log = logging.getLogger(__name__)


def _select_backend() -> str:
    """Return backend name from env vars with deprecation warning."""
    if "USAGE_METERING" in os.environ:
        return os.getenv("USAGE_METERING", "null")
    if "USAGE_BACKEND" in os.environ:  # old name, keep BC
        warnings.warn(
            "USAGE_BACKEND is deprecated; use USAGE_METERING",
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
        except ImportError as exc:
            log.warning(
                "Prometheus metering unavailable: %s – "
                "falling back to NullUsageBackend. "
                "Install with: pip install 'attach-dev[usage]'",
                exc
            )
            return NullUsageBackend()

    if kind == "openmeter":
        # fail-fast on bad config
        if not os.getenv("OPENMETER_API_KEY"):
            raise RuntimeError(
                "USAGE_METERING=openmeter requires OPENMETER_API_KEY. "
                "Set the variable or change USAGE_METERING=null to disable."
            )
        return OpenMeterBackend()  # exceptions inside bubble up

    return NullUsageBackend()
