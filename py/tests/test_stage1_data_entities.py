from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fin_agent.data.importer import (
    import_corporate_actions_file,
    import_fundamentals_file,
    import_ratings_file,
    query_fundamentals_as_of,
)
from fin_agent.storage.paths import RuntimePaths


class Stage1DataEntitiesTests(unittest.TestCase):
    def test_fundamentals_import_requires_published_at(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            csv_path = root / "fundamentals.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "symbol,published_at,pe_ratio,eps",
                        "ABC,,22.5,10.1",
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "published_at"):
                import_fundamentals_file(csv_path, RuntimePaths(root=root))

    def test_corporate_actions_import_requires_effective_at(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            csv_path = root / "corp.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "symbol,effective_at,action_type,action_value",
                        "ABC,,split,2.0",
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "effective_at"):
                import_corporate_actions_file(csv_path, RuntimePaths(root=root))

    def test_ratings_import_requires_revised_at(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            csv_path = root / "ratings.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "symbol,revised_at,agency,rating",
                        "ABC,,BankX,buy",
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "revised_at"):
                import_ratings_file(csv_path, RuntimePaths(root=root))

    def test_fundamentals_as_of_returns_latest_known_at_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            csv_path = root / "fundamentals.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "symbol,published_at,pe_ratio,eps",
                        "ABC,2025-01-01T00:00:00Z,20.0,5.0",
                        "ABC,2025-02-01T00:00:00Z,25.0,5.5",
                    ]
                ),
                encoding="utf-8",
            )
            paths = RuntimePaths(root=root)
            result = import_fundamentals_file(csv_path, paths)
            self.assertEqual(result.rows_inserted, 2)

            as_of = query_fundamentals_as_of(paths, symbol="ABC", as_of="2025-01-15T00:00:00Z")
            self.assertEqual(as_of["symbol"], "ABC")
            self.assertEqual(float(as_of["pe_ratio"]), 20.0)


if __name__ == "__main__":
    unittest.main()
