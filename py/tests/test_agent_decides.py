from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fin_agent.api import app as app_module
from fin_agent.storage import sqlite_store
from fin_agent.storage.paths import RuntimePaths


class AgentDecidesTests(unittest.TestCase):
    def _temp_paths(self) -> RuntimePaths:
        self._tmp = tempfile.TemporaryDirectory()
        paths = RuntimePaths(root=Path(self._tmp.name))
        sqlite_store.init_db(paths)
        return paths

    def tearDown(self) -> None:
        tmp = getattr(self, "_tmp", None)
        if tmp is not None:
            tmp.cleanup()

    def test_propose_marks_assumed_fields(self) -> None:
        with self.assertRaises(app_module.HTTPException) as ctx:
            app_module.brainstorm_agent_decides_propose(
                app_module.AgentDecidesProposeRequest(universe=["ABC"], short_window=5)
            )
        self.assertEqual(ctx.exception.status_code, 410)
        self.assertIn("legacy_endpoint_disabled", str(ctx.exception.detail))

    def test_confirm_persists_intent_and_decision_log(self) -> None:
        paths = self._temp_paths()
        request = app_module.AgentDecidesConfirmRequest(
            intent={
                "universe": ["ABC"],
                "start_date": "2025-01-01",
                "end_date": "2025-01-10",
                "initial_capital": 100000.0,
                "short_window": 2,
                "long_window": 4,
                "max_positions": 1,
            },
            decision_card=[
                app_module.DecisionCardItem(
                    field="universe",
                    value=["ABC"],
                    source="user_explicit",
                    rationale="provided directly by user",
                    confidence=1.0,
                )
            ],
        )
        with patch.object(app_module, "_runtime_paths", return_value=paths):
            with self.assertRaises(app_module.HTTPException) as ctx:
                app_module.brainstorm_agent_decides_confirm(request)
        self.assertEqual(ctx.exception.status_code, 410)
        self.assertIn("legacy_endpoint_disabled", str(ctx.exception.detail))


if __name__ == "__main__":
    unittest.main()
