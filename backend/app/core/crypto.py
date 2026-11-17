"""MultiFernet encryption for OAuth tokens at rest (docs/SECURITY.md §4)."""

from __future__ import annotations

import hashlib

from cryptography.fernet import Fernet, MultiFernet

from app.core.config import get_settings
from app.core.errors import IntegrationNotConnected


def _keys() -> list[str]:
    raw = get_settings().token_encryption_keys
    keys = [k.strip() for k in (raw.get_secret_value() if raw else "").split(",") if k.strip()]
    if not keys:
        raise IntegrationNotConnected("TOKEN_ENCRYPTION_KEYS is not configured.")
    return keys


def key_id(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:12]


def encrypt(plaintext: str) -> tuple[bytes, str]:
    keys = _keys()
    return MultiFernet([Fernet(k) for k in keys]).encrypt(plaintext.encode()), key_id(keys[0])


def decrypt(ciphertext: bytes) -> str:
    return MultiFernet([Fernet(k) for k in _keys()]).decrypt(ciphertext).decode()


def rotate(ciphertext: bytes) -> tuple[bytes, str]:
    keys = _keys()
    return MultiFernet([Fernet(k) for k in keys]).rotate(ciphertext), key_id(keys[0])


def generate_key() -> str:
    return Fernet.generate_key().decode()
