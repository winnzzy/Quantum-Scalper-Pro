"""Security primitive regression tests."""
from cryptography.fernet import Fernet

from app.core.security import (
    _derive_fernet_key,
    decrypt_secret,
    encrypt_secret,
)


def test_derived_fernet_key_is_valid_and_deterministic():
    secret = "your-super-secret-key-min-32-chars-long"

    first = _derive_fernet_key(secret)
    second = _derive_fernet_key(secret)

    assert first == second
    assert len(first) == 44
    Fernet(first)


def test_encrypted_secret_round_trip():
    plaintext = "broker-api-secret"

    encrypted = encrypt_secret(plaintext)

    assert encrypted != plaintext
    assert decrypt_secret(encrypted) == plaintext
