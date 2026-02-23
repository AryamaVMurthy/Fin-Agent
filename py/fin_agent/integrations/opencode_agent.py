from __future__ import annotations

import base64
import json
import os
import socket
from typing import Any
from urllib import error, parse, request


DEFAULT_OPENCODE_API = "http://127.0.0.1:4096"


def _opencode_api_base() -> str:
    raw = str(os.environ.get("OPENCODE_API", DEFAULT_OPENCODE_API)).strip()
    if not raw:
        raise ValueError("OPENCODE_API is empty")
    parsed = parse.urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"invalid OPENCODE_API URL: {raw}")
    return raw.rstrip("/")


def _opencode_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = dict(extra or {})
    username = os.environ.get("OPENCODE_SERVER_USERNAME", "opencode")
    password = os.environ.get("OPENCODE_SERVER_PASSWORD", "")
    if password:
        token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {token}"
    return headers


def _http_json(method: str, path: str, payload: dict[str, Any] | None, timeout_seconds: float) -> tuple[int, dict[str, Any]]:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    base_url = _opencode_api_base()
    body: bytes | None = None
    headers = _opencode_headers({"accept": "application/json"})
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["content-type"] = "application/json"

    req = request.Request(url=f"{base_url}{path}", method=method.upper(), data=body, headers=headers)
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            text = response.read().decode("utf-8", errors="replace")
            return int(response.getcode()), json.loads(text) if text else {}
    except TimeoutError as exc:
        raise ValueError(
            f"OpenCode request timed out after {timeout_seconds}s for path={path}; "
            "remediation: reduce prompt size, increase timeout, or verify OpenCode model responsiveness"
        ) from exc
    except socket.timeout as exc:
        raise ValueError(
            f"OpenCode request socket timeout after {timeout_seconds}s for path={path}; "
            "remediation: reduce prompt size, increase timeout, or verify OpenCode model responsiveness"
        ) from exc
    except error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(text) if text else {}
        except json.JSONDecodeError:
            parsed = {"detail": text}
        return int(exc.code), parsed
    except error.URLError as exc:
        raise ValueError(
            f"failed to reach OpenCode server at {base_url}: {exc.reason}; "
            "remediation: start opencode server mode and ensure OPENCODE_API is reachable"
        ) from exc


def _extract_assistant_text(message_payload: dict[str, Any]) -> str:
    parts = message_payload.get("parts", [])
    if not isinstance(parts, list):
        raise ValueError(f"invalid OpenCode message payload: parts is not list ({type(parts).__name__})")
    texts: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        if str(part.get("type", "")).lower() != "text":
            continue
        text_value = part.get("text")
        if text_value is None:
            continue
        texts.append(str(text_value))
    merged = "\n".join([chunk for chunk in texts if chunk.strip()])
    if not merged.strip():
        raise ValueError("OpenCode returned no assistant text content")
    return merged.strip()


def _parse_json_object(text: str) -> dict[str, Any]:
    raw = text.strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        pass
    else:
        if isinstance(parsed, dict):
            return parsed
        raise ValueError(f"agent response must be a JSON object, got {type(parsed).__name__}")

    # Accept fenced payloads to avoid silent degradation when the model wraps JSON in markdown.
    if "```" in raw:
        chunks = raw.split("```")
        for chunk in chunks:
            candidate = chunk.strip()
            if candidate.startswith("json"):
                candidate = candidate[4:].strip()
            if not candidate.startswith("{"):
                continue
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        candidate = raw[start : end + 1]
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "agent response is not valid JSON object; remediation: force strict JSON-only output"
            ) from exc
        if isinstance(parsed, dict):
            return parsed

    raise ValueError(
        "agent response missing JSON object; remediation: ensure prompt requires a JSON object only"
    )


def run_agent_json_task(
    *,
    user_prompt: str,
    system_prompt: str,
    timeout_seconds: float = 60.0,
    session_title: str = "Fin-Agent JSON task",
) -> dict[str, Any]:
    if not user_prompt.strip():
        raise ValueError("user_prompt is required")
    if not system_prompt.strip():
        raise ValueError("system_prompt is required")

    create_status, create_payload = _http_json(
        "POST",
        "/session",
        {"title": session_title},
        timeout_seconds=timeout_seconds,
    )
    if create_status >= 400:
        raise ValueError(
            f"OpenCode session create failed status={create_status} detail={create_payload}; "
            "remediation: verify OpenCode server auth/provider configuration"
        )

    session_id = str(create_payload.get("id", "")).strip()
    if not session_id:
        raise ValueError(
            f"OpenCode session create response missing id: {create_payload}; "
            "remediation: check OpenCode server compatibility/version"
        )

    message_status, message_payload = _http_json(
        "POST",
        f"/session/{parse.quote(session_id, safe='')}/message",
        {
            "parts": [{"type": "text", "text": user_prompt}],
            "system": system_prompt,
            "tools": {},
        },
        timeout_seconds=timeout_seconds,
    )
    if message_status >= 400:
        raise ValueError(
            f"OpenCode message failed status={message_status} detail={message_payload}; "
            "remediation: verify model/auth availability and retry"
        )

    assistant_text = _extract_assistant_text(message_payload)
    return _parse_json_object(assistant_text)
