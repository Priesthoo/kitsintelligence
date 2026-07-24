"""
Symmetric encryption for at-rest secrets (data-source credentials, PII
fields). Uses Fernet (AES-128-CBC + HMAC) with a key derived from
SECRET_KEY via HKDF, so no separate key-management infra is required for
the base deployment while still supporting external key rotation later.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings
from app.exceptions.base import AppException


def _derive_fernet_key() -> bytes:
    digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return base64.urlsafe_b64encode(digest)


_fernet = Fernet(_derive_fernet_key())


def encrypt_value(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    try:
        return _fernet.decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise AppException("Failed to decrypt stored credential", error_code="decryption_failed") from exc