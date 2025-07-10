from __future__ import annotations

import os
import time
from functools import lru_cache
from typing import Any

import httpx
from jose import jwt

from dotenv import load_dotenv
load_dotenv()

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


def _get_oidc_issuer() -> str:
    """Get OIDC issuer from environment, validated and normalized."""
    issuer = os.getenv("OIDC_ISSUER", "")
    if not issuer:
        raise RuntimeError("OIDC_ISSUER must be set (see README for setup)")
    return issuer


def _get_oidc_audience() -> str:
    """Get OIDC audience from environment, validated."""
    audience = os.getenv("OIDC_AUD", "")
    if not audience:
        raise RuntimeError("OIDC_AUD must be set (see README for setup)")
    return audience


@lru_cache(maxsize=1)
def _fetch_jwks(issuer: str) -> dict[str, Any]:
    """
    Download the issuer's JWKS once and keep it in memory.
    """
    # Remove trailing slash for URL construction, then add the path
    base_url = issuer.rstrip("/")
    url = f"{base_url}/.well-known/jwks.json"

    resp = httpx.get(url, timeout=5)
    resp.raise_for_status()

    return {"ts": time.time(), "keys": resp.json()["keys"]}


def _jwks(issuer: str) -> list[dict[str, Any]]:
    """
    Return the cached JWKS; refresh every 10 minutes.
    """
    cached = _fetch_jwks(issuer)
    if time.time() - cached["ts"] > 600:  # 10 min TTL
        _fetch_jwks.cache_clear()
        cached = _fetch_jwks(issuer)
    return cached["keys"]


async def _exchange_jwt_descope(
    external_jwt: str,
    external_issuer: str,
    # all optional for now - defaults are from original jwt
    # options: request / original / merged
    aud_src: Optional[str] = "original", 
    scope_src: Optional[str] = "original",
    custom_claims_src: Optional[str] = "original", 
) -> str:
    """
    Exchange an external JWT for a Descope token using inbound app token endpoint.
    """
    descope_base_url = os.getenv("DESCOPE_BASE_URL", "https://api.descope.com")
    descope_project_id = os.getenv("DESCOPE_PROJECT_ID")
    descope_client_id = os.getenv("DESCOPE_CLIENT_ID")
    descope_client_secret = os.getenv("DESCOPE_CLIENT_SECRET") # (not sure if need yet)
    external_issuer = os.getenv("OIDC_ISSUER") # part of grant req?

    token_endpoint = f"{descope_base_url}/oauth2/v1/apps/token" 

    grant_data = {
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",  
        "assertion": external_jwt,
        "client_id": descope_client_id,
        "client_secret": descope_client_secret,
        "issuer": external_issuer,
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            token_endpoint,
            data=grant_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        print(f"   Response Status: {response.status_code}")
        print(f"   Response Body: {response.text}")
            
        response.raise_for_status()
        return response.json()["access_token"]


def _verify_jwt_direct(token: str, *, leeway: int = 60) -> dict[str, Any]:
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
    # Read fresh environment variables each time
    issuer = _get_oidc_issuer()
    audience = _get_oidc_audience()

    # 1) Unverified header inspection
    header = jwt.get_unverified_header(token)
    alg = header.get("alg")
    if alg not in ACCEPTED_ALGS:
        raise ValueError(f"alg {alg!r} not allowed")

    kid = header.get("kid")
    if not kid:
        raise ValueError("JWT header missing 'kid'")

    # 2) Locate JWK (with one forced refresh on miss)
    keys = _jwks(issuer)
    key_cfg = next((k for k in keys if k["kid"] == kid), None)
    if not key_cfg:
        _fetch_jwks.cache_clear()
        keys = _jwks(issuer)
        key_cfg = next((k for k in keys if k["kid"] == kid), None)
        if not key_cfg:
            raise ValueError("signing key not found in issuer JWKS")

    # 3) Verify + decode
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


async def _verify_jwt_with_exchange(token: str, *, leeway: int = 60) -> dict[str, Any]:
    """
    Exchange an external JWT for a Descope token and verify it.
    """ 
    unverified_claims = jwt.get_unverified_claims(token)
    external_issuer = unverified_claims.get("iss")

    descope_token = await _exchange_jwt_descope(token, external_issuer)

    return _verify_jwt_direct(descope_token, leeway=leeway)


# --------------------------------------------------------------------------- #
# Public API                                                                  #
# --------------------------------------------------------------------------- #
async def verify_jwt(token: str, *, leeway: int = 60) -> dict[str, Any]:
    """
    Verify OIDC JWT - expects Descope tokens, exchanges external tokens.
    """
    try: 
        return _verify_jwt_direct(token, leeway=leeway)
    except Exception:
        try:
            return await _verify_jwt_with_exchange(token, leeway=leeway)
        except Exception as e:
            raise ValueError(f"JWT verification failed: {e}") from e
