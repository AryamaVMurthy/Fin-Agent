from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fin_agent.api import app as app_module
from fin_agent.storage.paths import RuntimePaths


CODE_A = """
def prepare(data_bundle, context):
    return {"variant": "A"}

def generate_signals(frame, state, context):
    return [{"symbol": "ABC", "signal": "buy", "strength": 0.64, "reason_code": "signal_buy_a"}]

def risk_rules(positions, context):
    return {"max_positions": 1}
"""

CODE_B = """
def prepare(data_bundle, context):
    return {"variant": "B"}

def generate_signals(frame, state, context):
    return [{"symbol": "ABC", "signal": "buy", "strength": 0.57, "reason_code": "signal_buy_b"}]

def risk_rules(positions, context):
    return {"max_positions": 1}
"""


class UiHistoryEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.paths = RuntimePaths(root=Path(self._tmp.name))

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

        with patch.object(app_module, "_runtime_paths", return_value=self.paths):
            app_module.startup()
            app_module.import_data(app_module.ImportRequest(path=str(csv_path)))

            one = app_module.code_strategy_backtest(
                app_module.CodeStrategyBacktestRequest(
                    strategy_name="History Run A",
                    source_code=CODE_A,
                    universe=["ABC"],
                    start_date="2025-01-01",
                    end_date="2025-01-10",
                    initial_capital=100000.0,
                )
            )
            two = app_module.code_strategy_backtest(
                app_module.CodeStrategyBacktestRequest(
                    strategy_name="History Run B",
                    source_code=CODE_B,
                    universe=["ABC"],
                    start_date="2025-01-01",
                    end_date="2025-01-10",
                    initial_capital=100000.0,
                )
            )
            self.backtest_run_id = one["run_id"]
            self.strategy_version_id = two["strategy_version_id"]

            app_module.live_activate(app_module.LiveActivateRequest(strategy_version_id=self.strategy_version_id))

            app_module.code_strategy_save(
                app_module.CodeStrategySaveRequest(strategy_name="Code History", source_code=CODE_A)
            )
            saved_two = app_module.code_strategy_save(
                app_module.CodeStrategySaveRequest(strategy_name="Code History", source_code=CODE_B)
            )
            self.code_strategy_id = saved_two["strategy_id"]

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_backtest_history_endpoints(self) -> None:
        with patch.object(app_module, "_runtime_paths", return_value=self.paths):
            runs = app_module.backtest_runs_list(limit=50)
            run_detail = app_module.backtest_run_detail(run_id=self.backtest_run_id)

        self.assertGreaterEqual(runs["count"], 2)
        self.assertEqual(run_detail["run_id"], self.backtest_run_id)
        self.assertIn("metrics", run_detail)

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

    def test_legacy_strategy_endpoints_are_disabled(self) -> None:
        with patch.object(app_module, "_runtime_paths", return_value=self.paths):
            with self.assertRaises(app_module.HTTPException) as ctx_one:
                app_module.strategies_list(limit=10)
            with self.assertRaises(app_module.HTTPException) as ctx_two:
                app_module.strategy_versions_list(strategy_id="anything", limit=10)
        self.assertEqual(ctx_one.exception.status_code, 410)
        self.assertEqual(ctx_two.exception.status_code, 410)


if __name__ == "__main__":
    unittest.main()
