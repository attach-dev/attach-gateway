import auth
import auth.did
import auth.oidc


def patch_router(monkeypatch):
    called = {}

    def fake_oidc(token: str, *, leeway: int = 60):
        called["oidc"] = token
        return {"sub": "oidc-user"}

    def fake_did(token: str, *, leeway: int = 60):
        called["did"] = token
        return {"sub": token}

    monkeypatch.setattr(auth.oidc, "verify_jwt", fake_oidc)
    monkeypatch.setattr(auth.did, "verify_jwt", fake_did)
    return called


def test_router_dispatches_to_oidc(monkeypatch):
    called = patch_router(monkeypatch)
    token = "a.b.c"
    result = auth.verify_jwt(token)
    assert result["sub"] == "oidc-user"
    assert called == {"oidc": token}


def test_router_dispatches_to_did(monkeypatch):
    called = patch_router(monkeypatch)
    token = "did:key:zabc"
    result = auth.verify_jwt(token)
    assert result["sub"] == token
    assert called == {"did": token}


def test_verify_did_accepts_key_and_pkh():
    did_key = "did:key:zabc"
    did_pkh = "did:pkh:eip155:1:0x123"

    assert auth.did.verify_jwt(did_key)["sub"] == did_key
    assert auth.did.verify_jwt(did_pkh)["sub"] == did_pkh


def test_verify_did_rejects_unknown_method():
    import pytest

    with pytest.raises(ValueError):
        auth.did.verify_jwt("did:web:example.com")
