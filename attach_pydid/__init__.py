from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DID:
    did: str
    method: str
    id: str

    def __str__(self) -> str:
        return self.did

    @classmethod
    def from_uri(cls, uri: str) -> "DID":
        if not uri.startswith("did:"):
            raise ValueError("invalid DID format")
        parts = uri.split(":", 2)
        if len(parts) < 3:
            raise ValueError("invalid DID format")
        method = parts[1]
        identifier = parts[2]
        return cls(uri, method, identifier)
