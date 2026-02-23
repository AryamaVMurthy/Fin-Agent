from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fin_agent.backtest.compare import compare_backtest_runs
from fin_agent.backtest.runner import run_backtest
from fin_agent.data.importer import import_ohlcv_file
from fin_agent.storage.paths import RuntimePaths
from fin_agent.strategy.models import IntentSnapshot
from fin_agent.strategy.service import build_strategy_from_intent
from fin_agent.world_state.service import build_world_state_manifest


class BacktestCompareTests(unittest.TestCase):
    def test_compare_runs_returns_deltas_and_artifact_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            csv_path = root / "prices.csv"
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

            paths = RuntimePaths(root=root)
            import_ohlcv_file(csv_path, paths)
            manifest = build_world_state_manifest(paths, universe=["ABC"], start_date="2025-01-01", end_date="2025-01-10")

            intent_a = IntentSnapshot(
                universe=["ABC"],
                start_date="2025-01-01",
                end_date="2025-01-10",
                initial_capital=100000.0,
                short_window=2,
                long_window=4,
                max_positions=1,
            )
            intent_b = IntentSnapshot(
                universe=["ABC"],
                start_date="2025-01-01",
                end_date="2025-01-10",
                initial_capital=100000.0,
                short_window=3,
                long_window=5,
                max_positions=1,
            )

            run_a = run_backtest(paths, build_strategy_from_intent(intent_a, strategy_name="SMA A"), manifest)
            run_b = run_backtest(paths, build_strategy_from_intent(intent_b, strategy_name="SMA B"), manifest)

            report = compare_backtest_runs(paths, baseline_run_id=run_a.run_id, candidate_run_id=run_b.run_id)

            self.assertEqual(report["baseline"]["run_id"], run_a.run_id)
            self.assertEqual(report["candidate"]["run_id"], run_b.run_id)
            self.assertIn("metrics_delta", report)
            self.assertIn("total_return", report["metrics_delta"])
            self.assertIn("artifact_links", report)
            self.assertIn("baseline", report["artifact_links"])
            self.assertIn("candidate", report["artifact_links"])
            self.assertGreaterEqual(len(report["likely_causes"]), 1)


if __name__ == "__main__":
    unittest.main()
