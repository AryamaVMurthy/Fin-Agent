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
        response = app_module.brainstorm_agent_decides_propose(
            app_module.AgentDecidesProposeRequest(universe=["ABC"], short_window=5)
        )
        self.assertIn("proposed_intent", response)
        decision_card = response["decision_card"]
        self.assertGreaterEqual(len(decision_card), 1)
        assumed = [row for row in decision_card if row["source"] == "agent_assumed"]
        self.assertGreaterEqual(len(assumed), 1)
        for row in assumed:
            self.assertTrue(row["rationale"])

    def test_confirm_persists_intent_and_decision_log(self) -> None:
        paths = self._temp_paths()
        propose = app_module.brainstorm_agent_decides_propose(
            app_module.AgentDecidesProposeRequest(universe=["ABC"])
        )

        request = app_module.AgentDecidesConfirmRequest(
            intent=app_module.IntentSnapshot.model_validate(propose["proposed_intent"]),
            decision_card=[app_module.DecisionCardItem.model_validate(item) for item in propose["decision_card"]],
        )
        with patch.object(app_module, "_runtime_paths", return_value=paths):
            result = app_module.brainstorm_agent_decides_confirm(request)

        snapshot = sqlite_store.get_intent_snapshot(paths, result["intent_snapshot_id"])
        self.assertEqual(snapshot["universe"], ["ABC"])
        events = sqlite_store.list_audit_events(paths, event_type="brainstorm.agent_decides.confirm")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["payload"]["intent_snapshot_id"], result["intent_snapshot_id"])


if __name__ == "__main__":
    unittest.main()
