from __future__ import annotations

import contextvars

_TRACE_ID: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="no-trace")


def get_trace_id() -> str:
    return _TRACE_ID.get()


def set_trace_id(trace_id: str) -> contextvars.Token[str]:
    return _TRACE_ID.set(trace_id)


def reset_trace_id(token: contextvars.Token[str]) -> None:
    _TRACE_ID.reset(token)
