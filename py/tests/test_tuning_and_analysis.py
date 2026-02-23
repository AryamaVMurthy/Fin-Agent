from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fin_agent.api import app as app_module
from fin_agent.storage.paths import RuntimePaths


VALID_CODE = """
def prepare(data_bundle, context):
    return {"prepared": True}

def generate_signals(frame, state, context):
    return [{"symbol": "ABC", "signal": "buy", "strength": 0.67, "reason_code": "signal_buy_analysis"}]

def risk_rules(positions, context):
    return {"max_positions": 1}
"""


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
            run = app_module.code_strategy_backtest(
                app_module.CodeStrategyBacktestRequest(
                    strategy_name="AnalysisLane",
                    source_code=VALID_CODE,
                    universe=["ABC"],
                    start_date="2025-01-01",
                    end_date="2025-01-10",
                    initial_capital=100000.0,
                )
            )
        self.run_id = run["run_id"]

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_tuning_search_space_endpoint_is_disabled(self) -> None:
        request = app_module.TuningSearchSpaceRequest(
            strategy_name="TuneMe",
            optimization_target="sharpe",
            risk_mode="balanced",
            policy_mode="agent_decides",
        )
        with patch.object(app_module, "_runtime_paths", return_value=self.paths):
            with self.assertRaises(app_module.HTTPException) as ctx:
                app_module.tuning_search_space_derive(request)
        self.assertEqual(ctx.exception.status_code, 410)
        self.assertIn("legacy_endpoint_disabled", str(ctx.exception.detail))

    def test_tuning_run_endpoint_is_disabled(self) -> None:
        request = app_module.TuningRunRequest(
            strategy_name="TuneRun",
            optimization_target="sharpe",
            risk_mode="balanced",
            policy_mode="agent_decides",
            max_trials=5,
        )
        with patch.object(app_module, "_runtime_paths", return_value=self.paths):
            with self.assertRaises(app_module.HTTPException) as ctx:
                app_module.tuning_run(request)
        self.assertEqual(ctx.exception.status_code, 410)
        self.assertIn("legacy_endpoint_disabled", str(ctx.exception.detail))

    def test_analysis_deep_dive_endpoint_is_disabled(self) -> None:
        request = app_module.AnalysisDeepDiveRequest(run_id=self.run_id)
        with patch.object(app_module, "_runtime_paths", return_value=self.paths):
            with self.assertRaises(app_module.HTTPException) as ctx:
                app_module.analysis_deep_dive(request)
        self.assertEqual(ctx.exception.status_code, 410)
        self.assertIn("legacy_endpoint_disabled", str(ctx.exception.detail))

    def test_code_analysis_suggestions_have_evidence(self) -> None:
        with patch.object(app_module, "_runtime_paths", return_value=self.paths):
            with patch(
                "fin_agent.code_strategy.analysis.run_agent_json_task",
                return_value={
                    "summary": "Agent analysis complete",
                    "suggestions": [
                        {
                            "title": "Reduce overfitting pressure",
                            "evidence": "trade concentration is high in signal preview",
                            "expected_impact": "Better out-of-sample resilience.",
                            "confidence": 0.74,
                            "patch": "if volatility < cap: signals.append({...})",
                        }
                    ],
                },
            ):
                report = app_module.code_strategy_analyze(
                    app_module.CodeStrategyAnalyzeRequest(
                        run_id=self.run_id,
                        source_code=VALID_CODE,
                        max_suggestions=5,
                    )
                )

        self.assertEqual(report["run_id"], self.run_id)
        self.assertGreaterEqual(report["suggestion_count"], 1)
        for suggestion in report["suggestions"]:
            self.assertTrue(suggestion["evidence"])
            self.assertTrue(suggestion["expected_impact"])
            self.assertGreaterEqual(float(suggestion["confidence"]), 0.0)
            self.assertLessEqual(float(suggestion["confidence"]), 1.0)


if __name__ == "__main__":
    unittest.main()
