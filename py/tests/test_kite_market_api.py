from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from fin_agent.api import app as app_module
from fin_agent.integrations import rate_limit as rate_limit_integration
from fin_agent.storage import duckdb_store, sqlite_store
from fin_agent.storage.paths import RuntimePaths


class KiteMarketApiTests(unittest.TestCase):
    def _temp_paths(self) -> RuntimePaths:
        self._tmp = tempfile.TemporaryDirectory()
        paths = RuntimePaths(root=Path(self._tmp.name))
        sqlite_store.init_db(paths)
        duckdb_store.init_db(paths)
        sqlite_store.upsert_connector_session(
            paths,
            connector="kite",
            payload={
                "connected_at": "2026-02-23T10:00:00+00:00",
                "token": {"access_token": "access-token-123"},
                "profile": {"user_id": "NAU670"},
            },
        )
        return paths

    def tearDown(self) -> None:
        tmp = getattr(self, "_tmp", None)
        if tmp is not None:
            tmp.cleanup()

    def _env(self) -> dict[str, str]:
        return {
            "FIN_AGENT_KITE_API_KEY": "kite_key",
            "FIN_AGENT_KITE_API_SECRET": "kite_secret",
            "FIN_AGENT_KITE_REDIRECT_URI": "http://127.0.0.1:8080/v1/auth/kite/callback",
        }

    def test_kite_candles_fetch_persists_rows(self) -> None:
        paths = self._temp_paths()
        candles = [
            {
                "timestamp": "2026-02-20T09:15:00+0530",
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 10000.0,
                "oi": None,
            }
        ]
        with patch.object(app_module, "_runtime_paths", return_value=paths):
            with patch.dict("os.environ", self._env(), clear=False):
                with patch("fin_agent.api.app.kite_integration.fetch_historical_candles", return_value=candles):
                    out = app_module.kite_candles_fetch(
                        app_module.KiteCandlesFetchRequest(
                            symbol="INFY",
                            instrument_token="123",
                            interval="5minute",
                            from_ts="2026-02-20 09:15:00",
                            to_ts="2026-02-20 15:30:00",
                            persist=True,
                        )
                    )
        self.assertEqual(out["persisted_rows"], 1)

    def test_kite_candles_fetch_cache_hit_skips_upstream(self) -> None:
        paths = self._temp_paths()
        candles = [
            {
                "timestamp": "2026-02-20T09:15:00+0530",
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 10000.0,
                "oi": None,
            }
        ]
        with patch.object(app_module, "_runtime_paths", return_value=paths):
            with patch.dict("os.environ", self._env(), clear=False):
                with patch("fin_agent.api.app.kite_integration.fetch_historical_candles", return_value=candles):
                    first = app_module.kite_candles_fetch(
                        app_module.KiteCandlesFetchRequest(
                            symbol="INFY",
                            instrument_token="123",
                            interval="5minute",
                            from_ts="2026-02-20 09:15:00",
                            to_ts="2026-02-20 15:30:00",
                            persist=True,
                            use_cache=True,
                        )
                    )
                self.assertFalse(first["cache_hit"])
                with patch(
                    "fin_agent.api.app.kite_integration.fetch_historical_candles",
                    side_effect=AssertionError("upstream should not be called on cache hit"),
                ):
                    second = app_module.kite_candles_fetch(
                        app_module.KiteCandlesFetchRequest(
                            symbol="INFY",
                            instrument_token="123",
                            interval="5minute",
                            from_ts="2026-02-20 09:15:00",
                            to_ts="2026-02-20 15:30:00",
                            persist=True,
                            use_cache=True,
                        )
                    )
        self.assertTrue(second["cache_hit"])
        self.assertEqual(second["rows"], 1)

    def test_kite_quotes_fetch_returns_payload(self) -> None:
        paths = self._temp_paths()
        with patch.object(app_module, "_runtime_paths", return_value=paths):
            with patch.dict("os.environ", self._env(), clear=False):
                with patch(
                    "fin_agent.api.app.kite_integration.fetch_ltp",
                    return_value={"NSE:INFY": {"instrument_token": 123, "last_price": 1700.5}},
                ):
                    out = app_module.kite_quotes_fetch(
                        app_module.KiteQuotesFetchRequest(instruments=["NSE:INFY"], persist=False)
                    )
        self.assertEqual(out["received"], 1)
        self.assertIn("NSE:INFY", out["quotes"])

    def test_kite_rate_limited_returns_http_429(self) -> None:
        paths = self._temp_paths()
        rate_limit_integration.reset_rate_limits()
        with patch.object(app_module, "_runtime_paths", return_value=paths):
            with patch.dict(
                "os.environ",
                {
                    **self._env(),
                    "FIN_AGENT_RATE_LIMIT_KITE_MAX_REQUESTS": "1",
                    "FIN_AGENT_RATE_LIMIT_KITE_WINDOW_SECONDS": "60",
                },
                clear=False,
            ):
                with patch("fin_agent.api.app.kite_integration.fetch_holdings", return_value=[]):
                    app_module.kite_holdings()
                    with self.assertRaises(HTTPException) as exc:
                        app_module.kite_holdings()
        self.assertEqual(exc.exception.status_code, 429)
        self.assertEqual(exc.exception.detail.get("code"), "provider_rate_limited")


if __name__ == "__main__":
    unittest.main()
