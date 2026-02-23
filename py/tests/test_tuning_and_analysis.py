from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fin_agent.api import app as app_module
from fin_agent.storage import sqlite_store
from fin_agent.storage.paths import RuntimePaths


class TuningAndAnalysisTests(unittest.TestCase):
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

        self.intent = app_module.IntentSnapshot(
            universe=["ABC"],
            start_date="2025-01-01",
            end_date="2025-01-10",
            initial_capital=100000.0,
            short_window=2,
            long_window=4,
            max_positions=1,
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_tuning_search_space_derivation(self) -> None:
        request = app_module.TuningSearchSpaceRequest(
            strategy_name="TuneMe",
            intent=self.intent,
            optimization_target="sharpe",
            risk_mode="balanced",
            policy_mode="agent_decides",
            max_drawdown_limit=0.20,
            turnover_cap=20,
        )
        with patch.object(app_module, "_runtime_paths", return_value=self.paths):
            payload = app_module.tuning_search_space_derive(request)

        self.assertIn("search_space", payload)
        self.assertIn("short_window", payload["search_space"])
        self.assertIn("constraints", payload)
        self.assertEqual(payload["constraints"]["turnover_cap"], 20)
        self.assertEqual(payload["constraints"]["max_drawdown_limit"], 0.20)
        self.assertIn("tuning_plan", payload)
        self.assertIn("layers", payload["tuning_plan"])
        self.assertIn("graph", payload["tuning_plan"])
        self.assertGreaterEqual(payload["estimated_trials"], 1)

    def test_tuning_search_space_user_selected_layers_freeze_others(self) -> None:
        request = app_module.TuningSearchSpaceRequest(
            strategy_name="TuneSelected",
            intent=self.intent,
            optimization_target="sharpe",
            risk_mode="balanced",
            policy_mode="user_selected",
            include_layers=["signal"],
        )
        with patch.object(app_module, "_runtime_paths", return_value=self.paths):
            payload = app_module.tuning_search_space_derive(request)

        self.assertEqual(payload["policy_mode"], "user_selected")
        self.assertEqual(payload["tuning_plan"]["active_layers"], ["signal"])
        self.assertGreater(len(payload["search_space"]["short_window"]), 1)
        self.assertGreater(len(payload["search_space"]["long_window"]), 1)
        self.assertEqual(payload["search_space"]["max_positions"], [1.0])
        self.assertEqual(payload["search_space"]["cost_bps"], [5.0])

    def test_tuning_search_space_invalid_layer_fails_fast(self) -> None:
        request = app_module.TuningSearchSpaceRequest(
            strategy_name="TuneInvalid",
            intent=self.intent,
            optimization_target="sharpe",
            risk_mode="balanced",
            policy_mode="user_selected",
            include_layers=["unknown_layer"],
        )
        with patch.object(app_module, "_runtime_paths", return_value=self.paths):
            with self.assertRaises(app_module.HTTPException) as ctx:
                app_module.tuning_search_space_derive(request)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("unsupported include_layers", str(ctx.exception.detail))

    def test_tuning_run_returns_best_candidate(self) -> None:
        request = app_module.TuningRunRequest(
            strategy_name="TuneRun",
            intent=self.intent,
            optimization_target="sharpe",
            risk_mode="balanced",
            policy_mode="agent_decides",
            max_drawdown_limit=0.30,
            turnover_cap=40,
            max_trials=5,
        )
        with patch.object(app_module, "_runtime_paths", return_value=self.paths):
            payload = app_module.tuning_run(request)

        self.assertIn("tuning_run_id", payload)
        self.assertIn("best_candidate", payload)
        self.assertGreaterEqual(payload["completed_trials"], 1)
        self.assertLessEqual(payload["completed_trials"], 5)
        self.assertIn("sensitivity_analysis", payload)
        self.assertIn("tuning_plan", payload)
        self.assertGreaterEqual(len(payload["sensitivity_analysis"]), 1)
        trial_rows = sqlite_store.list_tuning_trials(self.paths, payload["tuning_run_id"])
        layer_rows = sqlite_store.list_tuning_layer_decisions(self.paths, payload["tuning_run_id"])
        self.assertGreaterEqual(len(trial_rows), 1)
        self.assertGreaterEqual(len(layer_rows), 1)

    def test_analysis_deep_dive_suggestions_have_evidence(self) -> None:
        run_request = app_module.BacktestRequest(strategy_name="DeepDive", intent=self.intent)
        with patch.object(app_module, "_runtime_paths", return_value=self.paths):
            run_payload = app_module.backtest_run(run_request)
            report = app_module.analysis_deep_dive(
                app_module.AnalysisDeepDiveRequest(run_id=run_payload["run_id"])
            )

        self.assertEqual(report["run_id"], run_payload["run_id"])
        self.assertGreaterEqual(report["suggestion_count"], 1)
        for suggestion in report["suggestions"]:
            self.assertTrue(suggestion["evidence"])
            self.assertTrue(suggestion["expected_impact"])
            self.assertGreaterEqual(float(suggestion["confidence"]), 0.0)
            self.assertLessEqual(float(suggestion["confidence"]), 1.0)


if __name__ == "__main__":
    unittest.main()
