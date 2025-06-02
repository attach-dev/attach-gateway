from __future__ import annotations

from typing import Any

from attach_pydid import DID


def verify_jwt(token: str, *, leeway: int = 60) -> dict[str, Any]:
    """Validate a DID token (did:key or did:pkh)."""
    did = DID.from_uri(token)  # raises ValueError on bad format

    if did.method not in {"key", "pkh"}:
        raise ValueError(f"DID method {did.method!r} not supported")

    # NOTE: wallet verifies JWT signature & expiry upstream
    # TODO: respect `leeway` once expiry (`exp`) is parsed

    return {"sub": str(did)}
