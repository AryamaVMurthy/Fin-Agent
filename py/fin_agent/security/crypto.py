from __future__ import annotations

import os

_PREFIX = "enc:v1:"


def _fernet_or_raise():
    try:
        from cryptography.fernet import Fernet  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise ValueError(
            "encryption key configured but cryptography package missing; install cryptography to enable encrypted storage"
        ) from exc
    key = os.environ.get("FIN_AGENT_ENCRYPTION_KEY", "").strip()
    if not key:
        raise ValueError("FIN_AGENT_ENCRYPTION_KEY is required for encrypted storage")
    try:
        return Fernet(key.encode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("invalid FIN_AGENT_ENCRYPTION_KEY format for Fernet") from exc


def encryption_enabled() -> bool:
    return bool(os.environ.get("FIN_AGENT_ENCRYPTION_KEY", "").strip())


def encrypt_json(plain: str) -> str:
    f = _fernet_or_raise()
    token = f.encrypt(plain.encode("utf-8")).decode("utf-8")
    return f"{_PREFIX}{token}"


def decrypt_json(value: str) -> str:
    if not value.startswith(_PREFIX):
        return value
    token = value[len(_PREFIX):]
    f = _fernet_or_raise()
    return f.decrypt(token.encode("utf-8")).decode("utf-8")
