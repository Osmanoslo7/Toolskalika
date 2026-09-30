import hashlib
import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet

from .config import get_settings

_FALLBACK_KEY_PATH = Path(__file__).resolve().parent.parent / ".secret_key"


def _load_or_create_fallback_key() -> bytes:
    """Dev/local convenience: persist a generated key next to the app so
    restarts don't invalidate encrypted data. Set TOOLSKALIKA_SECRET_KEY in
    production instead of relying on this file.
    """
    if _FALLBACK_KEY_PATH.exists():
        return _FALLBACK_KEY_PATH.read_bytes()
    key = Fernet.generate_key()
    _FALLBACK_KEY_PATH.write_bytes(key)
    os.chmod(_FALLBACK_KEY_PATH, 0o600)
    return key


def _fernet() -> Fernet:
    settings = get_settings()
    key = settings.toolskalika_secret_key.encode() if settings.toolskalika_secret_key else None
    return Fernet(key or _load_or_create_fallback_key())


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()


def generate_personal_access_token() -> tuple[str, str]:
    """Returns (plaintext_token, sha256_hash). Only the hash is stored."""
    token = f"tka_{secrets.token_urlsafe(32)}"
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
