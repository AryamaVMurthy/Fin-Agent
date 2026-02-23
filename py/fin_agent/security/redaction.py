from __future__ import annotations

from typing import Any

_SECRET_KEYS = {
    "access_token",
    "refresh_token",
    "token",
    "authorization",
    "cookie",
    "sessionid",
    "api_key",
    "api_secret",
    "secret",
    "password",
}


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def redact_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        out: dict[str, Any] = {}
        for key, value in payload.items():
            k = str(key).lower()
            if any(secret in k for secret in _SECRET_KEYS):
                out[str(key)] = _mask(str(value))
            else:
                out[str(key)] = redact_payload(value)
        return out
    if isinstance(payload, list):
        return [redact_payload(item) for item in payload]
    return payload
