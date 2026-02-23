from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from fin_agent.integrations.kite import (
    KiteConfig,
    build_login_url,
    create_kite_session,
    fetch_historical_candles,
    fetch_holdings,
    fetch_instruments,
    fetch_ltp,
    load_kite_config_from_env,
)


class _FakeHTTPResponse:
    def __init__(self, payload: dict[str, object] | str) -> None:
        if isinstance(payload, str):
            self._bytes = payload.encode("utf-8")
        else:
            self._bytes = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._bytes

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:  # type: ignore[no-untyped-def]
        return False


class KiteIntegrationTests(unittest.TestCase):
    def test_load_config_requires_all_env_vars(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as exc:
                load_kite_config_from_env()
        self.assertIn("FIN_AGENT_KITE_API_KEY", str(exc.exception))
        self.assertIn("FIN_AGENT_KITE_API_SECRET", str(exc.exception))
        self.assertIn("FIN_AGENT_KITE_REDIRECT_URI", str(exc.exception))

    def test_build_login_url_contains_expected_query_params(self) -> None:
        config = KiteConfig(api_key="kite_key", api_secret="kite_secret", redirect_uri="http://127.0.0.1:8080/callback")
        login_url = build_login_url(config=config, state="state123")
        self.assertTrue(login_url.startswith("https://kite.zerodha.com/connect/login?"))
        self.assertIn("api_key=kite_key", login_url)
        self.assertIn("state=state123", login_url)
        self.assertIn("v=3", login_url)

    def test_create_kite_session_exchanges_token_and_fetches_profile(self) -> None:
        config = KiteConfig(api_key="kite_key", api_secret="kite_secret", redirect_uri="http://127.0.0.1:8080/callback")
        token_payload = {
            "status": "success",
            "data": {
                "access_token": "access-token-1234",
                "public_token": "public-token-1234",
                "login_time": "2026-02-23 09:00:00",
            },
        }
        profile_payload = {
            "status": "success",
            "data": {
                "user_id": "AB1234",
                "user_name": "Test User",
                "email": "test@example.com",
            },
        }
        with patch(
            "fin_agent.integrations.kite.urllib.request.urlopen",
            side_effect=[_FakeHTTPResponse(token_payload), _FakeHTTPResponse(profile_payload)],
        ):
            session = create_kite_session(config=config, request_token="request-token-xyz")

        self.assertIn("connected_at", session)
        self.assertEqual(session["token"]["access_token"], "access-token-1234")
        self.assertEqual(session["profile"]["user_id"], "AB1234")

    def test_fetch_holdings_returns_data_list(self) -> None:
        config = KiteConfig(api_key="kite_key", api_secret="kite_secret", redirect_uri="http://127.0.0.1:8080/callback")
        holdings_payload = {
            "status": "success",
            "data": [
                {"tradingsymbol": "INFY", "quantity": 10},
                {"tradingsymbol": "TCS", "quantity": 5},
            ],
        }
        with patch(
            "fin_agent.integrations.kite.urllib.request.urlopen",
            return_value=_FakeHTTPResponse(holdings_payload),
        ):
            holdings = fetch_holdings(config=config, access_token="access-token-1234")
        self.assertEqual(len(holdings), 2)
        self.assertEqual(holdings[0]["tradingsymbol"], "INFY")

    def test_fetch_instruments_returns_rows_from_csv(self) -> None:
        config = KiteConfig(api_key="kite_key", api_secret="kite_secret", redirect_uri="http://127.0.0.1:8080/callback")
        payload = "\n".join(
            [
                "instrument_token,exchange_token,tradingsymbol,name,last_price,expiry,strike,tick_size,lot_size,instrument_type,segment,exchange",
                "123,1,INFY,Infosys,0,,0,0.05,1,EQ,NSE,NSE",
            ]
        )
        with patch(
            "fin_agent.integrations.kite.urllib.request.urlopen",
            return_value=_FakeHTTPResponse(payload),
        ):
            rows = fetch_instruments(config=config, access_token="access-token-1234")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["tradingsymbol"], "INFY")

    def test_fetch_instruments_accepts_legacy_json_payload(self) -> None:
        config = KiteConfig(api_key="kite_key", api_secret="kite_secret", redirect_uri="http://127.0.0.1:8080/callback")
        payload = {
            "status": "success",
            "data": [
                {"instrument_token": 123, "tradingsymbol": "INFY", "exchange": "NSE", "segment": "NSE"},
            ],
        }
        with patch(
            "fin_agent.integrations.kite.urllib.request.urlopen",
            return_value=_FakeHTTPResponse(payload),
        ):
            rows = fetch_instruments(config=config, access_token="access-token-1234")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["tradingsymbol"], "INFY")

    def test_fetch_historical_candles_returns_rows(self) -> None:
        config = KiteConfig(api_key="kite_key", api_secret="kite_secret", redirect_uri="http://127.0.0.1:8080/callback")
        payload = {
            "status": "success",
            "data": {
                "candles": [
                    ["2026-02-20T09:15:00+0530", 100.0, 102.0, 99.0, 101.0, 10000],
                    ["2026-02-20T09:20:00+0530", 101.0, 103.0, 100.0, 102.0, 11000],
                ]
            },
        }
        with patch(
            "fin_agent.integrations.kite.urllib.request.urlopen",
            return_value=_FakeHTTPResponse(payload),
        ):
            rows = fetch_historical_candles(
                config=config,
                access_token="access-token-1234",
                instrument_token="123",
                interval="5minute",
                from_ts="2026-02-20 09:15:00",
                to_ts="2026-02-20 15:30:00",
            )
        self.assertEqual(len(rows), 2)
        self.assertEqual(float(rows[0]["close"]), 101.0)

    def test_fetch_ltp_returns_payload(self) -> None:
        config = KiteConfig(api_key="kite_key", api_secret="kite_secret", redirect_uri="http://127.0.0.1:8080/callback")
        payload = {
            "status": "success",
            "data": {
                "NSE:INFY": {"instrument_token": 123, "last_price": 1700.5},
            },
        }
        with patch(
            "fin_agent.integrations.kite.urllib.request.urlopen",
            return_value=_FakeHTTPResponse(payload),
        ):
            ltp = fetch_ltp(config=config, access_token="access-token-1234", instruments=["NSE:INFY"])
        self.assertIn("NSE:INFY", ltp)
        self.assertEqual(float(ltp["NSE:INFY"]["last_price"]), 1700.5)


if __name__ == "__main__":
    unittest.main()
