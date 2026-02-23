from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import duckdb

from fin_agent.data.importer import import_ohlcv_file
from fin_agent.storage.paths import RuntimePaths
from fin_agent.world_state.service import (
    build_data_completeness_report,
    validate_world_state_pit,
)


class WorldStateValidationTests(unittest.TestCase):
    def _seed_csv(self, root: Path) -> RuntimePaths:
        csv_path = root / "prices.csv"
        csv_path.write_text(
            "\n".join(
                [
                    "timestamp,symbol,open,high,low,close,volume",
                    "2025-01-01T00:00:00Z,ABC,100,101,99,100,1000",
                    "2025-01-02T00:00:00Z,ABC,100,102,99,101,1000",
                    "2025-01-03T00:00:00Z,XYZ,200,201,199,200,2000",
                    "2025-01-04T00:00:00Z,XYZ,200,202,199,201,2000",
                ]
            ),
            encoding="utf-8",
        )
        paths = RuntimePaths(root=root)
        import_ohlcv_file(csv_path, paths)
        return paths

    def test_completeness_report_lists_missing_instrument_and_feature(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = self._seed_csv(Path(tmp_dir))
            report = build_data_completeness_report(
                paths,
                universe=["ABC", "MISSING"],
                start_date="2025-01-01",
                end_date="2025-01-10",
                strict_mode=False,
            )
            self.assertEqual(report.total_symbols, 2)
            self.assertEqual(len(report.skipped_instruments), 1)
            self.assertEqual(report.skipped_instruments[0]["symbol"], "MISSING")
            self.assertEqual(report.fallback_reason, "critical_missing_ohlcv_rows")
            self.assertGreaterEqual(len(report.skipped_features), 1)

    def test_completeness_report_strict_mode_blocks_missing_ohlcv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = self._seed_csv(Path(tmp_dir))
            with self.assertRaises(ValueError) as exc:
                build_data_completeness_report(
                    paths,
                    universe=["ABC", "MISSING"],
                    start_date="2025-01-01",
                    end_date="2025-01-10",
                    strict_mode=True,
                )
            self.assertIn("strict completeness check failed", str(exc.exception))

    def test_validate_world_state_pit_detects_future_publication_leak(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = self._seed_csv(Path(tmp_dir))
            with duckdb.connect(str(paths.duckdb_path)) as conn:
                conn.execute(
                    "UPDATE market_ohlcv SET published_at = timestamp + INTERVAL 1 DAY WHERE symbol = 'ABC'"
                )
            with self.assertRaises(ValueError) as exc:
                validate_world_state_pit(
                    paths,
                    universe=["ABC", "XYZ"],
                    start_date="2025-01-01",
                    end_date="2025-01-10",
                    strict_mode=True,
                )
            self.assertIn("future publication leaks detected", str(exc.exception))

    def test_validate_world_state_pit_non_strict_returns_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = self._seed_csv(Path(tmp_dir))
            report = validate_world_state_pit(
                paths,
                universe=["ABC", "XYZ"],
                start_date="2025-01-01",
                end_date="2025-01-10",
                strict_mode=False,
            )
            self.assertTrue(report.valid)
            self.assertEqual(report.leak_rows, 0)

    def test_validate_world_state_pit_detects_missing_published_at(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = self._seed_csv(Path(tmp_dir))
            with duckdb.connect(str(paths.duckdb_path)) as conn:
                conn.execute("UPDATE market_ohlcv SET published_at = NULL WHERE symbol = 'ABC'")
            with self.assertRaises(ValueError) as exc:
                validate_world_state_pit(
                    paths,
                    universe=["ABC", "XYZ"],
                    start_date="2025-01-01",
                    end_date="2025-01-10",
                    strict_mode=True,
                )
            self.assertIn("published_at", str(exc.exception))


if __name__ == "__main__":
    unittest.main()
