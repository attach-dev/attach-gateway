from __future__ import annotations

import os
import time
from functools import lru_cache
from typing import Any

import httpx
from jose import jwt

# ---------------------------------------------------------------------------

ACCEPTED_ALGS: set[str] = {"RS256", "ES256"}


# --------------------------------------------------------------------------- #
# Internal helpers                                                            #
# --------------------------------------------------------------------------- #
def _require_env(var: str) -> str:
    """Abort startup if a mandatory env-var is missing."""
    val = os.getenv(var)
    if not val:
        raise RuntimeError(f"{var} must be set (see README for setup)")
    return val


@lru_cache(maxsize=1)
def _fetch_jwks() -> dict[str, Any]:
    """
    Download the issuer's JWKS once and keep it in memory.

    We wrap the payload together with the timestamp so we can implement a TTL
    on top of `lru_cache` (which by itself is size-based, not time-based).
    """
    issuer = _require_env("OIDC_ISSUER").rstrip("/")
    url = f"{issuer}/.well-known/jwks.json"

    resp = httpx.get(url, timeout=5)
    resp.raise_for_status()

    return {"ts": time.time(), "keys": resp.json()["keys"]}


def _jwks() -> list[dict[str, Any]]:
    """
    Return the cached JWKS; refresh every 10 minutes.
    """
    cached = _fetch_jwks()
    if time.time() - cached["ts"] > 600:  # 10 min TTL
        _fetch_jwks.cache_clear()
        cached = _fetch_jwks()
    return cached["keys"]


# --------------------------------------------------------------------------- #
# Public API                                                                  #
# --------------------------------------------------------------------------- #
def verify_jwt(token: str, *, leeway: int = 60) -> dict[str, Any]:
    """
    Validate a client-supplied JWT.

    • Accept only RS256 / ES256.
    • Enforce `aud` and `exp` with configurable leeway.
    • If `kid` is unknown, refresh JWKS once before failing.

    Returns:
        Decoded claim set (`dict[str, Any]`) on success.

    Raises:
        ValueError | jose.JWTError on any validation error.
    """
    # 1) Unverified header inspection
    header = jwt.get_unverified_header(token)
    alg = header.get("alg")
    if alg not in ACCEPTED_ALGS:
        raise ValueError(f"alg {alg!r} not allowed")

    kid = header.get("kid")
    if not kid:
        raise ValueError("JWT header missing 'kid'")

    # 2) Locate JWK (with one forced refresh on miss)
    keys = _jwks()
    key_cfg = next((k for k in keys if k["kid"] == kid), None)
    if not key_cfg:
        _fetch_jwks.cache_clear()
        keys = _jwks()
        key_cfg = next((k for k in keys if k["kid"] == kid), None)
        if not key_cfg:
            raise ValueError("signing key not found in issuer JWKS")

    # 3) Verify + decode
    issuer = _require_env("OIDC_ISSUER")
    audience = _require_env("OIDC_AUD")

    return jwt.decode(
        token,
        key_cfg,  # jose selects RSA/ECDSA key automatically
        algorithms=[alg],
        audience=audience,
        issuer=issuer,
        options={
            "leeway": leeway,
            "verify_aud": True,
            "verify_exp": True,
            "verify_iat": True,
        },
    )
