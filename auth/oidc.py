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


def _get_auth_backend() -> str:
    """Get authentication backend from environment."""
    return os.getenv("AUTH_BACKEND", "auth0")


def _get_jwks_url(issuer: str) -> str:
    """Get JWKS URL from environment or construct from issuer."""
    backend = _get_auth_backend()

    if backend == "descope":
        custom_jwks = os.getenv("DESCOPE_JWKS_URL")
        if custom_jwks:
            return custom_jwks

        project_id = _require_env("DESCOPE_PROJECT_ID")
        return f"https://api.descope.com/{project_id}/.well-known/jwks.json"
    else:
        if "api.descope.com/v1/apps/" in issuer:
            project_id = issuer.split("/")[-1] 
            return f"https://api.descope.com/{project_id}/.well-known/jwks.json"
        else:
            base_url = issuer.rstrip("/")
            return f"{base_url}/.well-known/jwks.json"


@lru_cache(maxsize=4)
def _fetch_jwks(issuer: str) -> dict[str, Any]:
    """
    Download the issuer's JWKS once and keep it in memory.
    """
    url = _get_jwks_url(issuer)

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
) -> str:
    """
    Exchange an external JWT for a Descope token using inbound app token endpoint.
    """
    descope_base_url = os.getenv("DESCOPE_BASE_URL", "https://api.descope.com")
    descope_project_id = _require_env("DESCOPE_PROJECT_ID")
    descope_client_id = _require_env("DESCOPE_CLIENT_ID")
    descope_client_secret = _require_env("DESCOPE_CLIENT_SECRET")

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

def _verify_jwt_against(token: str, issuer: str, *, audience: str, leeway: int = 60) -> dict[str, Any]:
    header = jwt.get_unverified_header(token)
    alg = header.get("alg")
    if alg not in ACCEPTED_ALGS:
        raise ValueError(f"alg {alg!r} not allowed")
    kid = header.get("kid")
    if not kid:
        raise ValueError("JWT header missing 'kid'")

    keys = _jwks(issuer)
    key_cfg = next((k for k in keys if k["kid"] == kid), None)
    if not key_cfg:
        _fetch_jwks.cache_clear()
        keys = _jwks(issuer)
        key_cfg = next((k for k in keys if k["kid"] == kid), None)
        if not key_cfg:
            raise ValueError("signing key not found in issuer JWKS")

    return jwt.decode(
        token, key_cfg, algorithms=[alg],
        audience=audience, issuer=issuer,
        options={"leeway": leeway, "verify_aud": True, "verify_exp": True, "verify_iat": True},
    )

async def verify_jwt_with_exchange(token: str, *, leeway: int = 60) -> dict[str, Any]:
    """
    Exchange an external JWT for a Descope token and verify it.

    First, tries to directly verify the JWT. Then, immediately throws on validation errors without attempting the exchange.

    Attempts the exchange. 

    Returns:
        Decoded claim set (`dict[str, Any]`) on success.

    Raises:
        ValueError | jose.JWTError on any validation error.
        ValueError if exchange fails.
        ValueError if exchange is not applicable (e.g., missing issuer).
    """ 
    try:
        return _verify_jwt_direct(token, leeway=leeway)
    except ValueError as direct_error:
        # Don't attempt exchange for validation errors like invalid algorithm or missing kid
        if any(phrase in str(direct_error) for phrase in [
            "not allowed", 
            "missing 'kid'", 
            "invalid token",
            "malformed",
            "expired"
        ]):
            raise direct_error
            
        try:
            unverified_claims = jwt.get_unverified_claims(token)
            external_issuer = unverified_claims.get("iss")
            
            if not external_issuer:
                raise ValueError("Cannot extract issuer from token for exchange")
            
            descope_token = await _exchange_jwt_descope(token, external_issuer)
            descope_issuer = f"https://api.descope.com/v1/apps/{_require_env('DESCOPE_PROJECT_ID')}"
            audience = os.getenv("DESCOPE_AUD", _get_oidc_audience())
            return _verify_jwt_against(descope_token, issuer=descope_issuer, audience=audience, leeway=leeway)
        except Exception as exchange_error:
            raise ValueError(f"JWT verification failed; direct={direct_error!s}; exchange={exchange_error!s}")
    except Exception as other_error:
        raise other_error



# --------------------------------------------------------------------------- #
# Public API                                                                  #
# --------------------------------------------------------------------------- #
def verify_jwt(token: str, *, leeway: int = 60) -> dict[str, Any]:
    """
    Backward-compatible JWT verification 
    async structure with exchange can be called with verify_jwt_with_exchange
    """
    return _verify_jwt_direct(token, leeway=leeway)