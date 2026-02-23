from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fin_agent.api import app as app_module
from fin_agent.storage.paths import RuntimePaths


class LiveAndVisualizationTests(unittest.TestCase):
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
        intent = app_module.IntentSnapshot(
            universe=["ABC"],
            start_date="2025-01-01",
            end_date="2025-01-10",
            initial_capital=100000.0,
            short_window=2,
            long_window=4,
            max_positions=1,
        )
        with patch.object(app_module, "_runtime_paths", return_value=self.paths):
            app_module.startup()
            app_module.import_data(app_module.ImportRequest(path=str(csv_path)))
            run_payload = app_module.backtest_run(app_module.BacktestRequest(strategy_name="LiveViz", intent=intent))
        self.run_id = run_payload["run_id"]
        self.strategy_version_id = run_payload["strategy_version_id"]

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_trade_blotter_and_signal_context(self) -> None:
        with patch.object(app_module, "_runtime_paths", return_value=self.paths):
            report = app_module.visualize_trade_blotter(app_module.TradeBlotterRequest(run_id=self.run_id))
        self.assertEqual(report["run_id"], self.run_id)
        self.assertIn("trade_blotter_path", report["artifacts"])
        self.assertIn("signal_context_path", report["artifacts"])
        self.assertTrue(Path(report["artifacts"]["trade_blotter_path"]).exists())
        self.assertTrue(Path(report["artifacts"]["signal_context_path"]).exists())

    def test_live_lifecycle_and_boundary_candidates(self) -> None:
        with patch.object(app_module, "_runtime_paths", return_value=self.paths):
            activated = app_module.live_activate(
                app_module.LiveActivateRequest(strategy_version_id=self.strategy_version_id)
            )
            feed = app_module.live_feed(strategy_version_id=self.strategy_version_id, limit=20)
            candidates_one = app_module.live_boundary_candidates(strategy_version_id=self.strategy_version_id, top_k=5)
            candidates_two = app_module.live_boundary_candidates(strategy_version_id=self.strategy_version_id, top_k=5)
            paused = app_module.live_pause(app_module.LiveLifecycleRequest(strategy_version_id=self.strategy_version_id))
            stopped = app_module.live_stop(app_module.LiveLifecycleRequest(strategy_version_id=self.strategy_version_id))

        self.assertEqual(activated["status"], "active")
        self.assertGreaterEqual(feed["count"], 1)
        self.assertEqual(candidates_one["candidates"], candidates_two["candidates"])
        self.assertEqual(paused["status"], "paused")
        self.assertEqual(stopped["status"], "stopped")

    def test_boundary_visualization_artifact(self) -> None:
        with patch.object(app_module, "_runtime_paths", return_value=self.paths):
            payload = app_module.visualize_boundary(
                app_module.BoundaryVisualizationRequest(strategy_version_id=self.strategy_version_id, top_k=5)
            )
        self.assertTrue(Path(payload["boundary_chart_path"]).exists())
        self.assertLessEqual(len(payload["candidates"]), 5)


if __name__ == "__main__":
    unittest.main()
