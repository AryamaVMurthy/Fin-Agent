from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderLimit:
    max_requests: int
    window_seconds: float


_LOCK = threading.Lock()
_STATE: dict[str, list[float]] = {}


def _read_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"invalid {name}: {raw}") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _read_float_env(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"invalid {name}: {raw}") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def provider_limit(provider: str) -> ProviderLimit:
    key = provider.strip().lower()
    if key == "kite":
        return ProviderLimit(
            max_requests=_read_int_env("FIN_AGENT_RATE_LIMIT_KITE_MAX_REQUESTS", 20),
            window_seconds=_read_float_env("FIN_AGENT_RATE_LIMIT_KITE_WINDOW_SECONDS", 1.0),
        )
    if key == "nse":
        return ProviderLimit(
            max_requests=_read_int_env("FIN_AGENT_RATE_LIMIT_NSE_MAX_REQUESTS", 10),
            window_seconds=_read_float_env("FIN_AGENT_RATE_LIMIT_NSE_WINDOW_SECONDS", 1.0),
        )
    if key == "tradingview":
        return ProviderLimit(
            max_requests=_read_int_env("FIN_AGENT_RATE_LIMIT_TRADINGVIEW_MAX_REQUESTS", 5),
            window_seconds=_read_float_env("FIN_AGENT_RATE_LIMIT_TRADINGVIEW_WINDOW_SECONDS", 1.0),
        )
    raise ValueError(f"unsupported provider for rate limit: {provider}")


def enforce_provider_limit(provider: str) -> dict[str, float | int]:
    cfg = provider_limit(provider)
    now = time.monotonic()
    with _LOCK:
        timestamps = [t for t in _STATE.get(provider, []) if (now - t) < cfg.window_seconds]
        if len(timestamps) >= cfg.max_requests:
            retry_after_seconds = max(0.0, cfg.window_seconds - (now - timestamps[0]))
            raise ValueError(
                f"provider_rate_limited provider={provider} retry_after_seconds={retry_after_seconds:.3f}"
            )
        timestamps.append(now)
        _STATE[provider] = timestamps
    return {
        "provider": provider,
        "max_requests": cfg.max_requests,
        "window_seconds": cfg.window_seconds,
        "remaining_in_window": max(0, cfg.max_requests - len(timestamps)),
    }


def reset_rate_limits() -> None:
    with _LOCK:
        _STATE.clear()
