from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fin_agent.storage import sqlite_store
from fin_agent.storage.paths import RuntimePaths


class SqliteOauthTests(unittest.TestCase):
    def test_oauth_state_consumed_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = RuntimePaths(root=Path(tmp_dir))
            sqlite_store.init_db(paths)
            sqlite_store.create_oauth_state(paths, connector="kite", state="state-123")

            sqlite_store.consume_oauth_state(paths, connector="kite", state="state-123", max_age_seconds=60)
            with self.assertRaises(ValueError) as exc:
                sqlite_store.consume_oauth_state(paths, connector="kite", state="state-123", max_age_seconds=60)

            self.assertIn("already consumed", str(exc.exception))

    def test_connector_session_upsert_and_get(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = RuntimePaths(root=Path(tmp_dir))
            sqlite_store.init_db(paths)
            payload = {
                "connected_at": "2026-02-23T10:00:00+00:00",
                "profile": {"user_id": "AB1234"},
                "token": {"access_token": "secret-token"},
            }
            sqlite_store.upsert_connector_session(paths, connector="kite", payload=payload)
            stored = sqlite_store.get_connector_session(paths, connector="kite")
            self.assertIsNotNone(stored)
            assert stored is not None
            self.assertEqual(stored["profile"]["user_id"], "AB1234")

    def test_consume_latest_oauth_state_requires_single_pending_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = RuntimePaths(root=Path(tmp_dir))
            sqlite_store.init_db(paths)
            sqlite_store.create_oauth_state(paths, connector="kite", state="state-1")
            sqlite_store.create_oauth_state(paths, connector="kite", state="state-2")

            with self.assertRaises(ValueError) as exc:
                sqlite_store.consume_latest_oauth_state(paths, connector="kite", max_age_seconds=60)
            self.assertIn("multiple pending oauth states", str(exc.exception))

    def test_consume_latest_oauth_state_happy_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = RuntimePaths(root=Path(tmp_dir))
            sqlite_store.init_db(paths)
            sqlite_store.create_oauth_state(paths, connector="kite", state="state-single")

            consumed = sqlite_store.consume_latest_oauth_state(paths, connector="kite", max_age_seconds=60)
            self.assertEqual(consumed, "state-single")


if __name__ == "__main__":
    unittest.main()
