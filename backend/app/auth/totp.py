"""Small RFC 6238 implementation for owner authenticator-app MFA."""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def generate_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _decode_secret(secret: str) -> bytes:
    padding = "=" * ((8 - len(secret) % 8) % 8)
    return base64.b32decode(secret + padding, casefold=True)


def generate_code(secret: str, at_time: int | None = None) -> str:
    counter = int((at_time if at_time is not None else time.time()) // 30)
    digest = hmac.new(
        _decode_secret(secret), struct.pack(">Q", counter), hashlib.sha1
    ).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{value:06d}"


def verify_code(secret: str, code: str, at_time: int | None = None) -> bool:
    if not code or len(code) != 6 or not code.isdigit():
        return False
    now = at_time if at_time is not None else int(time.time())
    return any(
        hmac.compare_digest(generate_code(secret, now + offset * 30), code)
        for offset in (-1, 0, 1)
    )


def provisioning_uri(secret: str, email: str) -> str:
    issuer = settings.APP_NAME
    label = quote(f"{issuer}:{email}")
    return (
        f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}"
        "&algorithm=SHA1&digits=6&period=30"
    )


def _cipher() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)


def encrypt_secret(secret: str) -> str:
    return _cipher().encrypt(secret.encode()).decode()


def decrypt_secret(token: str) -> str | None:
    try:
        return _cipher().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None
