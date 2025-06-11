from __future__ import annotations

__all__ = ["verify_jwt"]

from . import did, oidc


def verify_jwt(token: str, *, leeway: int = 60):
    """Dispatch token verification based on format."""
    if token.count(".") == 2:
        return oidc.verify_jwt(token, leeway=leeway)
    return did.verify_jwt(token, leeway=leeway)
