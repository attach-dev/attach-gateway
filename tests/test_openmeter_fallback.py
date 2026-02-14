"""
Test OpenMeter non-fatal fallback.

When USAGE_METERING=openmeter but OPENMETER_API_KEY is not set,
the gateway should start successfully with NullUsageBackend (not crash).
"""

import os

import pytest

# Must set OIDC env vars before importing gateway
os.environ["OIDC_ISSUER"] = "https://test.auth0.com/"
os.environ["OIDC_AUD"] = "test-api"


def test_openmeter_without_api_key_does_not_crash(monkeypatch):
    """
    Test that setting USAGE_METERING=openmeter without OPENMETER_API_KEY
    does not crash the gateway; it should fallback to NullUsageBackend.
    """
    monkeypatch.setenv("USAGE_METERING", "openmeter")
    monkeypatch.delenv("OPENMETER_API_KEY", raising=False)

    from usage.backends import NullUsageBackend
    from usage.factory import _select_backend, get_usage_backend

    # Should not raise RuntimeError
    backend_selector = _select_backend()
    backend = get_usage_backend(backend_selector)

    # Should fallback to NullUsageBackend
    assert isinstance(backend, NullUsageBackend)


def test_openmeter_with_api_key_uses_openmeter(monkeypatch):
    """
    Test that setting USAGE_METERING=openmeter with OPENMETER_API_KEY
    uses OpenMeterBackend.
    """
    monkeypatch.setenv("USAGE_METERING", "openmeter")
    monkeypatch.setenv("OPENMETER_API_KEY", "test-key")

    from usage.backends import OpenMeterBackend
    from usage.factory import _select_backend, get_usage_backend

    backend_selector = _select_backend()
    backend = get_usage_backend(backend_selector)

    # Should use OpenMeterBackend
    assert isinstance(backend, OpenMeterBackend)


def test_null_usage_backend_by_default(monkeypatch):
    """
    Test that default (no USAGE_METERING set) uses NullUsageBackend.
    """
    monkeypatch.delenv("USAGE_METERING", raising=False)
    monkeypatch.delenv("USAGE_BACKEND", raising=False)

    from usage.backends import NullUsageBackend
    from usage.factory import _select_backend, get_usage_backend

    backend_selector = _select_backend()
    backend = get_usage_backend(backend_selector)

    assert isinstance(backend, NullUsageBackend)
