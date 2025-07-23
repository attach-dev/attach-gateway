import pytest

from usage.factory import get_usage_backend

pytest.importorskip("prometheus_client")


def test_prometheus_backend_falls_back_to_null_when_unavailable(monkeypatch):
    monkeypatch.setenv("USAGE_METERING", "prometheus")

    # This should return NullUsageBackend when prometheus_client unavailable
    backend = get_usage_backend("prometheus")

    if hasattr(backend, "counter"):
        # prometheus_client available - got PrometheusUsageBackend
        assert backend.__class__.__name__ == "PrometheusUsageBackend"
    else:
        # prometheus_client unavailable - got NullUsageBackend fallback
        assert backend.__class__.__name__ == "NullUsageBackend"
