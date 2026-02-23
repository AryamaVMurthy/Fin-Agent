from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

NSE_QUOTES_URL = "https://www.nseindia.com/api/quote-equity"


def fetch_nse_equity_quote(symbol: str, timeout_seconds: float = 15.0) -> dict[str, Any]:
    key = symbol.strip().upper()
    if not key:
        raise ValueError("symbol is required")
    req = urllib.request.Request(
        url=f"{NSE_QUOTES_URL}?symbol={key}",
        method="GET",
        headers={
            "User-Agent": "fin-agent/0.1",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ValueError(f"nse_http_error status={exc.code} detail={detail}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"nse_network_error detail={exc.reason}") from exc

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("nse_invalid_json_response") from exc
    if not isinstance(parsed, dict):
        raise ValueError("nse_invalid_payload_object")
    return parsed
