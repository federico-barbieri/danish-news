"""Optional HTTP basic auth, enabled when BASIC_AUTH_USER and BASIC_AUTH_HASH are set.

Hash format: ``scrypt:<salt_hex>:<hash_hex>`` (no ``$``, so it survives .env / Compose / Coolify).
Generate one with: ``uv run python -m app.auth 'your-password'``
"""
import base64
import hashlib
import hmac
import os
import sys

_N, _R, _P = 2**14, 8, 1


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P)
    return f"scrypt:{salt.hex()}:{digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, hash_hex = stored.split(":")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=_N, r=_R, p=_P)
        return hmac.compare_digest(digest, bytes.fromhex(hash_hex))
    except ValueError:
        return False


class BasicAuth:
    def __init__(self, user: str, stored_hash: str):
        self.user = user
        self.stored_hash = stored_hash
        self._ok: set[str] = set()  # sha256 of Authorization headers already verified

    def check(self, header: str | None) -> bool:
        if not header or not header.lower().startswith("basic "):
            return False
        key = hashlib.sha256(header.encode()).hexdigest()
        if key in self._ok:
            return True
        try:
            user, _, password = base64.b64decode(header[6:]).decode().partition(":")
        except ValueError:
            return False
        ok = hmac.compare_digest(user.encode(), self.user.encode()) and verify_password(password, self.stored_hash)
        if ok:
            self._ok.add(key)
        return ok


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m app.auth '<password>'")
    print(hash_password(sys.argv[1]))
