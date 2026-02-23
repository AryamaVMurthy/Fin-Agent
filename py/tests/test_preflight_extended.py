from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fin_agent.analysis.preflight import (
    enforce_custom_code_budget,
    enforce_tuning_budget,
    enforce_world_state_budget,
)
from fin_agent.data.importer import import_ohlcv_file
from fin_agent.storage.paths import RuntimePaths


class PreflightExtendedTests(unittest.TestCase):
    def _seed(self) -> RuntimePaths:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        csv_path = root / "prices.csv"
        csv_path.write_text(
            "\n".join(
                [
                    "timestamp,symbol,open,high,low,close,volume",
                    "2025-01-01T00:00:00Z,ABC,100,101,99,100,1000",
                    "2025-01-02T00:00:00Z,ABC,100,102,99,101,1000",
                    "2025-01-03T00:00:00Z,ABC,101,104,100,103,1200",
                    "2025-01-04T00:00:00Z,ABC,103,105,102,104,1200",
                    "2025-01-05T00:00:00Z,ABC,104,106,103,105,1300",
                ]
            ),
            encoding="utf-8",
        )
        paths = RuntimePaths(root=root)
        import_ohlcv_file(csv_path, paths)
        return paths

    def tearDown(self) -> None:
        tmp = getattr(self, "_tmp", None)
        if tmp is not None:
            tmp.cleanup()

    def test_world_state_preflight_exceeds_budget(self) -> None:
        paths = self._seed()
        with self.assertRaises(ValueError) as exc:
            enforce_world_state_budget(paths, ["ABC"], "2025-01-01", "2025-01-05", max_estimated_seconds=0.00001)
        self.assertIn("preflight budget exceeded", str(exc.exception))

    def test_tuning_preflight_budget_and_success(self) -> None:
        with self.assertRaises(ValueError):
            enforce_tuning_budget(num_trials=100, per_trial_estimated_seconds=1.0, max_estimated_seconds=20.0)
        result = enforce_tuning_budget(num_trials=10, per_trial_estimated_seconds=1.0, max_estimated_seconds=20.0)
        self.assertGreater(result["estimated_seconds"], 0)

    def test_custom_code_preflight_budget(self) -> None:
        paths = self._seed()
        with self.assertRaises(ValueError):
            enforce_custom_code_budget(
                paths,
                universe=["ABC"],
                start_date="2025-01-01",
                end_date="2025-01-05",
                complexity_multiplier=2.0,
                max_estimated_seconds=0.00001,
            )
        result = enforce_custom_code_budget(
            paths,
            universe=["ABC"],
            start_date="2025-01-01",
            end_date="2025-01-05",
            complexity_multiplier=1.0,
            max_estimated_seconds=10.0,
        )
        self.assertGreater(result["estimated_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
