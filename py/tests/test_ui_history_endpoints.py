from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fin_agent.api import app as app_module
from fin_agent.code_strategy.validator import validate_code_strategy_source
from fin_agent.storage import sqlite_store
from fin_agent.storage.paths import RuntimePaths


VALID_CODE = """
def prepare(data_bundle, context):
    return {"prepared": True}

def generate_signals(frame, state, context):
    return [{"symbol": "ABC", "signal": "buy", "strength": 0.8}]

def risk_rules(positions, context):
    return {"max_positions": 5}
"""


class UiHistoryEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.paths = RuntimePaths(root=Path(self._tmp.name))
        self.fixed_strategy_id = "strategy-fixed-history"

        csv_path = Path(self._tmp.name) / "prices.csv"
        csv_path.write_text(
            "\n".join(
                [
                    "timestamp,symbol,open,high,low,close,volume",
                    "2025-01-01T00:00:00Z,ABC,100,101,99,100,1000",
                    "2025-01-02T00:00:00Z,ABC,100,102,99,101,1100",
                    "2025-01-03T00:00:00Z,ABC,101,104,100,103,1200",
                    "2025-01-04T00:00:00Z,ABC,103,105,102,104,1200",
                    "2025-01-05T00:00:00Z,ABC,104,106,103,105,1300",
                    "2025-01-06T00:00:00Z,ABC,105,107,104,106,1300",
                    "2025-01-07T00:00:00Z,ABC,106,106,100,101,1400",
                    "2025-01-08T00:00:00Z,ABC,101,103,99,100,1400",
                    "2025-01-09T00:00:00Z,ABC,100,102,98,99,1500",
                    "2025-01-10T00:00:00Z,ABC,99,101,97,98,1500",
                ]
            ),
            encoding="utf-8",
        )

        self.intent_a = app_module.IntentSnapshot(
            universe=["ABC"],
            start_date="2025-01-01",
            end_date="2025-01-10",
            initial_capital=100000.0,
            short_window=2,
            long_window=4,
            max_positions=1,
        )
        self.intent_b = app_module.IntentSnapshot(
            universe=["ABC"],
            start_date="2025-01-01",
            end_date="2025-01-10",
            initial_capital=100000.0,
            short_window=3,
            long_window=5,
            max_positions=1,
        )

        with patch.object(app_module, "_runtime_paths", return_value=self.paths):
            app_module.startup()
            app_module.import_data(app_module.ImportRequest(path=str(csv_path)))

            one = app_module.backtest_run(app_module.BacktestRequest(strategy_name="History Run A", intent=self.intent_a))
            two = app_module.backtest_run(app_module.BacktestRequest(strategy_name="History Run B", intent=self.intent_b))
            self.backtest_run_id = one["run_id"]
            self.strategy_version_id = two["strategy_version_id"]

            tuning = app_module.tuning_run(
                app_module.TuningRunRequest(
                    strategy_name="History Tune",
                    intent=self.intent_a,
                    max_trials=2,
                    per_trial_estimated_seconds=0.01,
                )
            )
            self.tuning_run_id = tuning["tuning_run_id"]

            app_module.live_activate(app_module.LiveActivateRequest(strategy_version_id=self.strategy_version_id))

            app_module.code_strategy_save(
                app_module.CodeStrategySaveRequest(strategy_name="Code History", source_code=VALID_CODE)
            )
            saved_two = app_module.code_strategy_save(
                app_module.CodeStrategySaveRequest(strategy_name="Code History", source_code=VALID_CODE)
            )
            self.code_strategy_id = saved_two["strategy_id"]

            spec_v1 = {
                "strategy_id": self.fixed_strategy_id,
                "strategy_name": "Manual History Strategy",
                "universe": ["ABC"],
                "start_date": "2025-01-01",
                "end_date": "2025-01-10",
                "initial_capital": 100000.0,
                "signal_type": "sma_crossover",
                "short_window": 2,
                "long_window": 5,
                "max_positions": 1,
                "cost_bps": 5.0,
            }
            spec_v2 = {
                **spec_v1,
                "short_window": 3,
            }
            sqlite_store.save_strategy_version(self.paths, "Manual History Strategy", spec_v1)
            sqlite_store.save_strategy_version(self.paths, "Manual History Strategy", spec_v2)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_strategies_and_versions_history_endpoints(self) -> None:
        with patch.object(app_module, "_runtime_paths", return_value=self.paths):
            strategies = app_module.strategies_list(limit=50)
            versions = app_module.strategy_versions_list(strategy_id=self.fixed_strategy_id, limit=10)

        self.assertGreaterEqual(strategies["count"], 1)
        matched = [row for row in strategies["strategies"] if row["strategy_id"] == self.fixed_strategy_id]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["latest_version_number"], 2)
        self.assertEqual(versions["strategy_id"], self.fixed_strategy_id)
        self.assertEqual(versions["count"], 2)
        self.assertEqual(versions["versions"][0]["version_number"], 2)

    def test_backtest_and_tuning_history_endpoints(self) -> None:
        with patch.object(app_module, "_runtime_paths", return_value=self.paths):
            runs = app_module.backtest_runs_list(limit=50)
            run_detail = app_module.backtest_run_detail(run_id=self.backtest_run_id)
            tuning_runs = app_module.tuning_runs_list(limit=50)
            tuning_detail = app_module.tuning_run_detail(tuning_run_id=self.tuning_run_id)

        self.assertGreaterEqual(runs["count"], 2)
        self.assertEqual(run_detail["run_id"], self.backtest_run_id)
        self.assertIn("metrics", run_detail)
        self.assertGreaterEqual(tuning_runs["count"], 1)
        self.assertEqual(tuning_detail["tuning_run_id"], self.tuning_run_id)
        self.assertGreaterEqual(len(tuning_detail["trials"]), 1)
        self.assertGreaterEqual(len(tuning_detail["layer_decisions"]), 1)

    def test_live_and_code_strategy_history_endpoints(self) -> None:
        with patch.object(app_module, "_runtime_paths", return_value=self.paths):
            live_states = app_module.live_states_list(limit=20)
            live_state = app_module.live_state_detail(strategy_version_id=self.strategy_version_id)
            code_strategies = app_module.code_strategies_list(limit=20)
            code_versions = app_module.code_strategy_versions_list(strategy_id=self.code_strategy_id, limit=20)

        self.assertGreaterEqual(live_states["count"], 1)
        self.assertEqual(live_state["strategy_version_id"], self.strategy_version_id)
        self.assertEqual(live_state["status"], "active")
        self.assertGreaterEqual(code_strategies["count"], 1)
        self.assertEqual(code_versions["strategy_id"], self.code_strategy_id)
        self.assertEqual(code_versions["count"], 2)
        self.assertEqual(code_versions["versions"][0]["version_number"], 2)
        self.assertIn("validation", code_versions["versions"][0])


if __name__ == "__main__":
    unittest.main()
