import tempfile
import unittest
from pathlib import Path


class ImporterTests(unittest.TestCase):
    def test_import_ohlcv_requires_columns(self) -> None:
        from fin_agent.data.importer import import_ohlcv_file
        from fin_agent.storage.paths import RuntimePaths

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            csv_path = root / "bad.csv"
            csv_path.write_text("timestamp,symbol,open,high,close,volume\n", encoding="utf-8")
            paths = RuntimePaths(root=root)

            with self.assertRaisesRegex(ValueError, "missing required columns"):
                import_ohlcv_file(csv_path, paths)

    def test_import_ohlcv_success(self) -> None:
        from fin_agent.data.importer import import_ohlcv_file
        from fin_agent.storage.duckdb_store import query_ohlcv_count
        from fin_agent.storage.paths import RuntimePaths

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            csv_path = root / "ok.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "timestamp,symbol,open,high,low,close,volume",
                        "2025-01-01T00:00:00Z,ABC,100,102,99,101,1000",
                        "2025-01-02T00:00:00Z,ABC,101,103,100,102,1100",
                    ]
                ),
                encoding="utf-8",
            )
            paths = RuntimePaths(root=root)
            result = import_ohlcv_file(csv_path, paths)

            self.assertEqual(result.rows_inserted, 2)
            self.assertEqual(query_ohlcv_count(paths, "ABC"), 2)


if __name__ == "__main__":
    unittest.main()

