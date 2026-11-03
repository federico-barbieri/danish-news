import base64

from app.auth import BasicAuth, hash_password, verify_password


def _hdr(u: str, p: str) -> str:
    return "Basic " + base64.b64encode(f"{u}:{p}".encode()).decode()


def test_hash_roundtrip_and_format():
    h = hash_password("hemmeligt")
    assert "$" not in h and h.startswith("scrypt:")
    assert verify_password("hemmeligt", h)
    assert not verify_password("forkert", h)
    assert not verify_password("x", "garbage")


def test_basic_auth_check():
    a = BasicAuth("me", hash_password("pw:with:colons"))
    assert a.check(_hdr("me", "pw:with:colons"))
    assert a.check(_hdr("me", "pw:with:colons"))  # cached path
    assert not a.check(_hdr("me", "nope"))
    assert not a.check(_hdr("you", "pw:with:colons"))
    assert not a.check(None)
    assert not a.check("Basic !!!notbase64")
