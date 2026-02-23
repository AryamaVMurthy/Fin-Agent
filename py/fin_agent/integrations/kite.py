from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

KITE_LOGIN_URL = "https://kite.zerodha.com/connect/login"
KITE_TOKEN_URL = "https://api.kite.trade/session/token"
KITE_PROFILE_URL = "https://api.kite.trade/user/profile"
KITE_HOLDINGS_URL = "https://api.kite.trade/portfolio/holdings"
KITE_INSTRUMENTS_URL = "https://api.kite.trade/instruments"
KITE_QUOTE_LTP_URL = "https://api.kite.trade/quote/ltp"


@dataclass(frozen=True)
class KiteConfig:
    api_key: str
    api_secret: str
    redirect_uri: str


def load_kite_config_from_env() -> KiteConfig:
    api_key = os.environ.get("FIN_AGENT_KITE_API_KEY", "").strip()
    api_secret = os.environ.get("FIN_AGENT_KITE_API_SECRET", "").strip()
    redirect_uri = os.environ.get("FIN_AGENT_KITE_REDIRECT_URI", "").strip()

    missing: list[str] = []
    if not api_key:
        missing.append("FIN_AGENT_KITE_API_KEY")
    if not api_secret:
        missing.append("FIN_AGENT_KITE_API_SECRET")
    if not redirect_uri:
        missing.append("FIN_AGENT_KITE_REDIRECT_URI")
    if missing:
        raise ValueError(f"missing required Kite env vars: {', '.join(missing)}")

    return KiteConfig(api_key=api_key, api_secret=api_secret, redirect_uri=redirect_uri)


def build_login_url(config: KiteConfig, state: str) -> str:
    if not state:
        raise ValueError("state is required")
    query = urllib.parse.urlencode(
        {
            "v": "3",
            "api_key": config.api_key,
            "state": state,
        }
    )
    return f"{KITE_LOGIN_URL}?{query}"


def generate_oauth_state() -> str:
    return uuid.uuid4().hex


def create_kite_session(config: KiteConfig, request_token: str, timeout_seconds: float = 15.0) -> dict[str, Any]:
    token = exchange_request_token(config, request_token=request_token, timeout_seconds=timeout_seconds)
    access_token = str(token.get("access_token", "")).strip()
    if not access_token:
        raise ValueError("Kite token response missing access_token")
    profile = fetch_profile(config, access_token=access_token, timeout_seconds=timeout_seconds)
    return {
        "connected_at": datetime.now(timezone.utc).isoformat(),
        "token": token,
        "profile": profile,
    }


def exchange_request_token(config: KiteConfig, request_token: str, timeout_seconds: float = 15.0) -> dict[str, Any]:
    if not request_token:
        raise ValueError("request_token is required")

    checksum = hashlib.sha256(
        f"{config.api_key}{request_token}{config.api_secret}".encode("utf-8")
    ).hexdigest()
    payload = urllib.parse.urlencode(
        {
            "api_key": config.api_key,
            "request_token": request_token,
            "checksum": checksum,
        }
    ).encode("utf-8")

    response = _http_json(
        url=KITE_TOKEN_URL,
        method="POST",
        body=payload,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Kite-Version": "3",
        },
        timeout_seconds=timeout_seconds,
    )
    if response.get("status") != "success":
        raise ValueError(f"Kite token exchange failed: {response}")
    data = response.get("data")
    if not isinstance(data, dict):
        raise ValueError("Kite token exchange response missing data payload")
    return data


def fetch_profile(config: KiteConfig, access_token: str, timeout_seconds: float = 15.0) -> dict[str, Any]:
    if not access_token:
        raise ValueError("access_token is required")
    response = _http_json(
        url=KITE_PROFILE_URL,
        method="GET",
        headers={
            "Authorization": f"token {config.api_key}:{access_token}",
            "X-Kite-Version": "3",
        },
        timeout_seconds=timeout_seconds,
    )
    if response.get("status") != "success":
        raise ValueError(f"Kite profile fetch failed: {response}")
    data = response.get("data")
    if not isinstance(data, dict):
        raise ValueError("Kite profile response missing data payload")
    return data


def fetch_holdings(config: KiteConfig, access_token: str, timeout_seconds: float = 15.0) -> list[dict[str, Any]]:
    if not access_token:
        raise ValueError("access_token is required")
    response = _http_json(
        url=KITE_HOLDINGS_URL,
        method="GET",
        headers={
            "Authorization": f"token {config.api_key}:{access_token}",
            "X-Kite-Version": "3",
        },
        timeout_seconds=timeout_seconds,
    )
    if response.get("status") != "success":
        raise ValueError(f"Kite holdings fetch failed: {response}")
    data = response.get("data")
    if not isinstance(data, list):
        raise ValueError("Kite holdings response missing data list payload")
    clean: list[dict[str, Any]] = []
    for row in data:
        if not isinstance(row, dict):
            raise ValueError("Kite holdings row is not an object")
        clean.append(row)
    return clean


def fetch_instruments(
    config: KiteConfig,
    access_token: str,
    exchange: str | None = None,
    timeout_seconds: float = 30.0,
) -> list[dict[str, Any]]:
    if not access_token:
        raise ValueError("access_token is required")
    url = KITE_INSTRUMENTS_URL
    if exchange:
        url = f"{url}/{urllib.parse.quote(exchange.strip())}"
    payload = _http_text(
        url=url,
        method="GET",
        headers={
            "Authorization": f"token {config.api_key}:{access_token}",
            "X-Kite-Version": "3",
        },
        timeout_seconds=timeout_seconds,
    )

    # Legacy/local mock compatibility: accept JSON payload if present.
    stripped = payload.lstrip()
    if stripped.startswith("{"):
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Kite instruments JSON parse failed: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("Kite instruments JSON payload must be an object")
        if parsed.get("status") != "success":
            raise ValueError(f"Kite instruments fetch failed: {parsed}")
        data = parsed.get("data")
        if not isinstance(data, list):
            raise ValueError("Kite instruments JSON response missing data list payload")
        rows: list[dict[str, Any]] = []
        for row in data:
            if not isinstance(row, dict):
                raise ValueError("Kite instruments row is not an object")
            rows.append(row)
        return rows

    reader = csv.DictReader(io.StringIO(payload))
    if not reader.fieldnames:
        raise ValueError("Kite instruments CSV response missing header row")
    missing_columns = [col for col in ("instrument_token", "tradingsymbol", "exchange", "segment") if col not in reader.fieldnames]
    if missing_columns:
        raise ValueError(f"Kite instruments CSV missing required columns: {missing_columns}")

    rows: list[dict[str, Any]] = []
    for row in reader:
        if not isinstance(row, dict):
            raise ValueError("Kite instruments CSV row is not an object")
        # DictReader returns OrderedDict[str, str|None]; normalize to plain str values.
        normalized: dict[str, Any] = {}
        for key, value in row.items():
            normalized[str(key)] = "" if value is None else str(value)
        rows.append(normalized)
    if not rows:
        raise ValueError("Kite instruments CSV returned zero rows")
    return rows


def fetch_historical_candles(
    config: KiteConfig,
    access_token: str,
    instrument_token: str,
    interval: str,
    from_ts: str,
    to_ts: str,
    continuous: int = 0,
    oi: int = 0,
    timeout_seconds: float = 30.0,
) -> list[dict[str, Any]]:
    if not access_token:
        raise ValueError("access_token is required")
    if not instrument_token.strip():
        raise ValueError("instrument_token is required")
    if not interval.strip():
        raise ValueError("interval is required")
    if not from_ts.strip() or not to_ts.strip():
        raise ValueError("from_ts and to_ts are required")
    query = urllib.parse.urlencode(
        {
            "from": from_ts,
            "to": to_ts,
            "continuous": int(continuous),
            "oi": int(oi),
        }
    )
    url = f"https://api.kite.trade/instruments/historical/{urllib.parse.quote(instrument_token)}/{urllib.parse.quote(interval)}?{query}"
    response = _http_json(
        url=url,
        method="GET",
        headers={
            "Authorization": f"token {config.api_key}:{access_token}",
            "X-Kite-Version": "3",
        },
        timeout_seconds=timeout_seconds,
    )
    if response.get("status") != "success":
        raise ValueError(f"Kite historical candles fetch failed: {response}")
    data = response.get("data")
    if not isinstance(data, dict):
        raise ValueError("Kite historical candles response missing data payload")
    candles = data.get("candles")
    if not isinstance(candles, list):
        raise ValueError("Kite historical candles response missing candles list")
    rows: list[dict[str, Any]] = []
    for item in candles:
        if not isinstance(item, list) or len(item) < 6:
            raise ValueError("Kite candle row must be list with at least 6 values")
        rows.append(
            {
                "timestamp": item[0],
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "volume": float(item[5]),
                "oi": float(item[6]) if len(item) > 6 and item[6] is not None else None,
            }
        )
    return rows


def fetch_ltp(
    config: KiteConfig,
    access_token: str,
    instruments: list[str],
    timeout_seconds: float = 15.0,
) -> dict[str, dict[str, Any]]:
    if not access_token:
        raise ValueError("access_token is required")
    if not instruments:
        raise ValueError("instruments must not be empty")
    query = urllib.parse.urlencode({"i": instruments}, doseq=True)
    response = _http_json(
        url=f"{KITE_QUOTE_LTP_URL}?{query}",
        method="GET",
        headers={
            "Authorization": f"token {config.api_key}:{access_token}",
            "X-Kite-Version": "3",
        },
        timeout_seconds=timeout_seconds,
    )
    if response.get("status") != "success":
        raise ValueError(f"Kite LTP fetch failed: {response}")
    data = response.get("data")
    if not isinstance(data, dict):
        raise ValueError("Kite LTP response missing data object")
    clean: dict[str, dict[str, Any]] = {}
    for key, value in data.items():
        if not isinstance(value, dict):
            raise ValueError(f"Kite LTP row is not an object for key={key}")
        clean[str(key)] = value
    return clean


def mask_secret(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return ""
    if len(stripped) <= 8:
        return "*" * len(stripped)
    return f"{stripped[:4]}...{stripped[-4:]}"


def _http_json(
    url: str,
    method: str,
    headers: dict[str, str],
    timeout_seconds: float,
    body: bytes | None = None,
) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    req = urllib.request.Request(url=url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ValueError(f"http_error status={exc.code} url={url} detail={detail}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"network_error url={url} detail={exc.reason}") from exc

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid_json_response url={url} payload={payload}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"invalid_json_object_response url={url}")
    return parsed


def _http_text(
    url: str,
    method: str,
    headers: dict[str, str],
    timeout_seconds: float,
    body: bytes | None = None,
) -> str:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    req = urllib.request.Request(url=url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ValueError(f"http_error status={exc.code} url={url} detail={detail}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"network_error url={url} detail={exc.reason}") from exc
    if not payload.strip():
        raise ValueError(f"empty_response url={url}")
    return payload
