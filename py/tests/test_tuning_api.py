from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fin_agent.api import app as app_module
from fin_agent.storage.paths import RuntimePaths


TUNING_CODE = """
def prepare(data_bundle, context):
    return {"symbols": data_bundle.get("universe", [])}


def generate_signals(frame, state, context):
    symbols = state.get("symbols", [])
    if not symbols:
        return []
    return [{"symbol": symbols[0], "signal": "buy", "strength": 0.6, "reason_code": "signal_buy"}]


def risk_rules(positions, context):
    params = context.get("tuning_params", {}) if isinstance(context, dict) else {}
    max_positions = params.get("max_positions", 1)
    return {"max_positions": int(max_positions) if max_positions else 1}
"""


class TuningApiTests(unittest.TestCase):
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
                ]
            ),
            encoding="utf-8",
        )
        with patch.object(app_module, "_runtime_paths", return_value=self.paths):
            app_module.startup()
            app_module.import_data(app_module.ImportRequest(path=str(csv_path)))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _tuning_request(self, only_plan: bool = False, run_async: bool = False) -> app_module.TuningRunRequest:
        return app_module.TuningRunRequest(
            strategy_name="Tuning API",
            source_code=TUNING_CODE,
            universe=["ABC"],
            start_date="2025-01-01",
            end_date="2025-01-05",
            initial_capital=100000.0,
            search_space={
                "max_positions": {
                    "type": "int_range",
                    "min": 1,
                    "max": 2,
                }
            },
            objective={"metric": "sharpe", "maximize": True},
            max_trials=1,
            max_layers=1,
            keep_top=1,
            timeout_seconds=3,
            memory_mb=128,
            cpu_seconds=1,
            max_estimated_seconds=60.0,
            only_plan=only_plan,
            run_async=run_async,
        )

    def test_sync_tuning_run_executes_and_persists(self) -> None:
        with patch.object(app_module, "_runtime_paths", return_value=self.paths):
            payload = app_module.create_tuning_run(self._tuning_request(only_plan=False, run_async=False))

        self.assertEqual(payload["result"]["status"], "completed")
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["request"]["strategy_name"], "Tuning API")
        self.assertGreaterEqual(payload["result"]["trials_attempted"], 1)

        with patch.object(app_module, "_runtime_paths", return_value=self.paths):
            detail = app_module.tuning_run_detail(payload["tuning_run_id"])
            list_payload = app_module.tuning_runs_list(limit=10)

        self.assertEqual(detail["tuning_run_id"], payload["tuning_run_id"])
        self.assertGreaterEqual(len(detail["trials"]), 1)
        self.assertGreaterEqual(list_payload["count"], 1)
        self.assertIn("best_score", list_payload["runs"][0])

    def test_async_tuning_run_updates_job_and_detail(self) -> None:
        with patch.object(app_module, "_runtime_paths", return_value=self.paths):
            payload = app_module.create_tuning_run(self._tuning_request(only_plan=False, run_async=True))
            tuning_run_id = payload["tuning_run_id"]
            job_id = payload["job_id"]
            detail = app_module.tuning_run_detail(tuning_run_id)
            self.assertEqual(detail["payload"]["status"], "running")

            for _ in range(80):
                job = app_module.job_status(job_id)
                if job["status"] in {"completed", "failed"}:
                    break
                time.sleep(0.05)
            self.assertIn(job["status"], {"completed", "failed"})
            if job["status"] == "failed":
                self.fail(f"async tuning failed: {job['error_text']}")

            updated_detail = app_module.tuning_run_detail(tuning_run_id)
            self.assertEqual(updated_detail["payload"]["status"], "completed")
            self.assertGreaterEqual(updated_detail["payload"]["result"]["trials_attempted"], 1)


if __name__ == "__main__":
    unittest.main()
