from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

TRADINGVIEW_INDIA_SCAN_URL = "https://scanner.tradingview.com/india/scan"


def _cookie_header_from_env() -> str:
    session = os.environ.get("FIN_AGENT_TRADINGVIEW_SESSIONID", "").strip()
    if not session:
        raise ValueError(
            "missing TradingView session; set FIN_AGENT_TRADINGVIEW_SESSIONID in .env.local"
        )
    return f"sessionid={session}"


def run_tradingview_scan(
    where: list[dict[str, Any]] | None = None,
    columns: list[str] | None = None,
    limit: int = 50,
    timeout_seconds: float = 20.0,
) -> dict[str, Any]:
    if limit <= 0:
        raise ValueError("limit must be positive")

    payload = {
        "filter": where or [],
        "options": {"lang": "en"},
        "symbols": {"query": {"types": []}, "tickers": []},
        "columns": columns or ["name", "close", "volume"],
        "sort": {"sortBy": "volume", "sortOrder": "desc"},
        "range": [0, limit],
    }

    req = urllib.request.Request(
        url=TRADINGVIEW_INDIA_SCAN_URL,
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Origin": "https://www.tradingview.com",
            "Referer": "https://www.tradingview.com/",
            "Cookie": _cookie_header_from_env(),
            "User-Agent": "fin-agent/0.1",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ValueError(f"tradingview_http_error status={exc.code} detail={detail}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"tradingview_network_error detail={exc.reason}") from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("tradingview_invalid_json_response") from exc
    if not isinstance(parsed, dict):
        raise ValueError("tradingview_invalid_payload_object")
    return parsed
