from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from fin_agent.api import app as app_module
from fin_agent.storage import sqlite_store
from fin_agent.storage.paths import RuntimePaths


class KiteApiTests(unittest.TestCase):
    def _temp_paths(self) -> RuntimePaths:
        self._tmp = tempfile.TemporaryDirectory()
        paths = RuntimePaths(root=Path(self._tmp.name))
        sqlite_store.init_db(paths)
        return paths

    def tearDown(self) -> None:
        tmp = getattr(self, "_tmp", None)
        if tmp is not None:
            tmp.cleanup()

    def test_kite_profile_requires_connected_session(self) -> None:
        paths = self._temp_paths()
        with patch.object(app_module, "_runtime_paths", return_value=paths):
            with patch.dict(
                "os.environ",
                {
                    "FIN_AGENT_KITE_API_KEY": "kite_key",
                    "FIN_AGENT_KITE_API_SECRET": "kite_secret",
                    "FIN_AGENT_KITE_REDIRECT_URI": "http://127.0.0.1:8080/v1/auth/kite/callback",
                },
                clear=False,
            ):
                with self.assertRaises(HTTPException) as exc:
                    app_module.kite_profile()
        self.assertEqual(exc.exception.status_code, 401)
        self.assertIn("reauth_required", str(exc.exception.detail))

    def test_kite_profile_uses_stored_access_token(self) -> None:
        paths = self._temp_paths()
        sqlite_store.upsert_connector_session(
            paths,
            connector="kite",
            payload={
                "connected_at": "2026-02-23T10:00:00+00:00",
                "token": {"access_token": "access-token-123"},
                "profile": {"user_id": "NAU670"},
            },
        )

        with patch.object(app_module, "_runtime_paths", return_value=paths):
            with patch.dict(
                "os.environ",
                {
                    "FIN_AGENT_KITE_API_KEY": "kite_key",
                    "FIN_AGENT_KITE_API_SECRET": "kite_secret",
                    "FIN_AGENT_KITE_REDIRECT_URI": "http://127.0.0.1:8080/v1/auth/kite/callback",
                },
                clear=False,
            ):
                with patch("fin_agent.api.app.kite_integration.fetch_profile", return_value={"user_id": "NAU670"}) as mocked:
                    response = app_module.kite_profile()

        self.assertEqual(response["connector"], "kite")
        self.assertEqual(response["profile"]["user_id"], "NAU670")
        mocked.assert_called_once()

    def test_kite_holdings_maps_token_errors_to_reauth_required(self) -> None:
        paths = self._temp_paths()
        sqlite_store.upsert_connector_session(
            paths,
            connector="kite",
            payload={
                "connected_at": "2026-02-23T10:00:00+00:00",
                "token": {"access_token": "expired-token"},
                "profile": {"user_id": "NAU670"},
            },
        )

        with patch.object(app_module, "_runtime_paths", return_value=paths):
            with patch.dict(
                "os.environ",
                {
                    "FIN_AGENT_KITE_API_KEY": "kite_key",
                    "FIN_AGENT_KITE_API_SECRET": "kite_secret",
                    "FIN_AGENT_KITE_REDIRECT_URI": "http://127.0.0.1:8080/v1/auth/kite/callback",
                },
                clear=False,
            ):
                with patch(
                    "fin_agent.api.app.kite_integration.fetch_holdings",
                    side_effect=ValueError("Kite holdings fetch failed: TokenException"),
                ):
                    with self.assertRaises(HTTPException) as exc:
                        app_module.kite_holdings()

        self.assertEqual(exc.exception.status_code, 401)
        self.assertIn("reauth_required", str(exc.exception.detail))


if __name__ == "__main__":
    unittest.main()
