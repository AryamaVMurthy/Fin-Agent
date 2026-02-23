from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fin_agent.api import app as app_module
from fin_agent.storage.paths import RuntimePaths


class SessionRehydrateTests(unittest.TestCase):
    def test_session_snapshot_and_rehydrate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = RuntimePaths(root=Path(tmp_dir) / ".finagent")
            with patch.object(app_module, "_runtime_paths", return_value=paths):
                snap = app_module.session_snapshot(
                    app_module.SessionSnapshotRequest(
                        session_id="sess-1",
                        state={"last_strategy_id": "s1", "last_formula": "close > open"},
                    )
                )
                self.assertEqual(snap["session_id"], "sess-1")

                out = app_module.session_rehydrate(app_module.SessionRehydrateRequest(session_id="sess-1"))
                self.assertEqual(out["session_id"], "sess-1")
                self.assertEqual(out["state"]["last_strategy_id"], "s1")

    def test_session_diff_reports_changed_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = RuntimePaths(root=Path(tmp_dir) / ".finagent")
            with patch.object(app_module, "_runtime_paths", return_value=paths):
                app_module.session_snapshot(
                    app_module.SessionSnapshotRequest(
                        session_id="sess-2",
                        state={"a": 1, "nested": {"x": 1, "y": 2}},
                    )
                )
                app_module.session_snapshot(
                    app_module.SessionSnapshotRequest(
                        session_id="sess-2",
                        state={"a": 2, "nested": {"x": 1, "y": 3}, "b": "new"},
                    )
                )
                out = app_module.session_diff(session_id="sess-2")
                self.assertEqual(out["session_id"], "sess-2")
                self.assertGreaterEqual(len(out["changes"]), 2)
                changed_paths = {item["path"] for item in out["changes"]}
                self.assertIn("a", changed_paths)
                self.assertIn("nested.y", changed_paths)


if __name__ == "__main__":
    unittest.main()
