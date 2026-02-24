from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fin_agent.storage import sqlite_store
from fin_agent.storage.paths import RuntimePaths


class TuningStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.paths = RuntimePaths(root=Path(self._tmp.name))
        sqlite_store.init_db(self.paths)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_save_tuning_run_persists_trials_and_layer_decisions(self) -> None:
        payload = {
            "tuning_run_id": "run-1",
            "evaluated_candidates": [
                {
                    "run_id": "bt-1",
                    "params": {"short_window": 2.0, "long_window": 4.0, "max_positions": 1.0, "cost_bps": 5.0},
                    "metrics": {"sharpe": 1.2, "cagr": 0.15, "total_return": 0.20},
                    "score": 1.2,
                }
            ],
            "tuning_plan": {
                "layers": [
                    {
                        "layer": "signal",
                        "enabled": True,
                        "parameters": ["short_window", "long_window"],
                        "reason": "active_with_variable_parameters",
                    }
                ]
            },
        }
        run_id = sqlite_store.save_tuning_run(self.paths, strategy_name="Tuning Strategy", payload=payload)
        self.assertEqual(run_id, "run-1")

        trials = sqlite_store.list_tuning_trials(self.paths, run_id)
        self.assertEqual(len(trials), 1)
        self.assertEqual(trials[0]["backtest_run_id"], "bt-1")
        self.assertAlmostEqual(float(trials[0]["score"]), 1.2)

        decisions = sqlite_store.list_tuning_layer_decisions(self.paths, run_id)
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]["layer_name"], "signal")
        self.assertTrue(decisions[0]["enabled"])

    def test_save_tuning_run_fails_on_invalid_candidate_payload(self) -> None:
        payload = {
            "tuning_run_id": "run-2",
            "evaluated_candidates": [
                {
                    "params": {"short_window": 2.0},
                    "metrics": {"sharpe": 1.0},
                    "score": 1.0,
                }
            ],
        }
        with self.assertRaises(ValueError) as ctx:
            sqlite_store.save_tuning_run(self.paths, strategy_name="Invalid", payload=payload)
        self.assertIn("missing run_id", str(ctx.exception))

    def test_update_tuning_run_merges_payload(self) -> None:
        run_id = sqlite_store.save_tuning_run(
            self.paths,
            strategy_name="Update Test",
            payload={
                "tuning_run_id": "run-3",
                "status": "queued",
                "request": {"max_trials": 4},
                "result": {"status": "queued"},
            },
        )
        sqlite_store.update_tuning_run(
            self.paths,
            tuning_run_id=run_id,
            updates={"status": "running", "result": {"status": "running", "stage": "executing"}},
        )
        tuning = sqlite_store.get_tuning_run(self.paths, tuning_run_id=run_id)
        self.assertEqual(tuning["payload"]["status"], "running")
        self.assertEqual(tuning["payload"]["result"]["status"], "running")
        self.assertEqual(tuning["payload"]["result"]["stage"], "executing")

    def test_append_tuning_trial_and_layer_persistence(self) -> None:
        base_run_id = sqlite_store.save_tuning_run(
            self.paths,
            strategy_name="Append Test",
            payload={
                "tuning_run_id": "run-4",
                "status": "running",
                "result": {"status": "running"},
            },
        )
        sqlite_store.append_tuning_trial(
            self.paths,
            tuning_run_id=base_run_id,
            backtest_run_id="bt-1",
            params={"short_window": 5},
            metrics={"sharpe": 1.2},
            score=1.2,
        )
        sqlite_store.append_tuning_layer_decision(
            self.paths,
            tuning_run_id=base_run_id,
            layer_name="layer_0",
            enabled=True,
            reason="initial sweep",
            payload={"attempted": 1},
        )

        trials = sqlite_store.list_tuning_trials(self.paths, base_run_id)
        layers = sqlite_store.list_tuning_layer_decisions(self.paths, base_run_id)
        self.assertEqual(len(trials), 1)
        self.assertEqual(trials[0]["backtest_run_id"], "bt-1")
        self.assertEqual(len(layers), 1)
        self.assertEqual(layers[0]["layer_name"], "layer_0")

    def test_append_tuning_trial_rejects_invalid_inputs(self) -> None:
        base_run_id = sqlite_store.save_tuning_run(
            self.paths,
            strategy_name="Invalid Append",
            payload={"tuning_run_id": "run-5", "status": "running", "result": {"status": "running"}},
        )
        with self.assertRaises(ValueError) as ctx:
            sqlite_store.append_tuning_trial(
                self.paths,
                tuning_run_id=base_run_id,
                backtest_run_id="",
                params={"short_window": 5},
                metrics={"sharpe": 1.2},
                score=1.2,
            )
        self.assertIn("backtest_run_id is required", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
