from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from fin_agent.api import app as app_module
from fin_agent.storage.paths import RuntimePaths


class VisualRegressionArtifactTests(unittest.TestCase):
    def test_boundary_svg_has_stable_structure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            paths = RuntimePaths(root=root / ".finagent")
            prices = root / "prices.csv"
            prices.write_text(
                "\n".join(
                    [
                        "timestamp,symbol,open,high,low,close,volume",
                        "2025-01-01T00:00:00Z,ABC,100,102,99,101,1000",
                        "2025-01-02T00:00:00Z,ABC,101,103,100,102,1000",
                        "2025-01-03T00:00:00Z,ABC,102,104,101,103,1000",
                        "2025-01-04T00:00:00Z,ABC,103,105,102,104,1000",
                    ]
                ),
                encoding="utf-8",
            )

            from unittest.mock import patch

            with patch.object(app_module, "_runtime_paths", return_value=paths):
                app_module.import_data(app_module.ImportRequest(path=str(prices)))
                run = app_module.backtest_run(
                    app_module.BacktestRequest(
                        strategy_name="Visual",
                        intent=app_module.IntentSnapshot(
                            universe=["ABC"],
                            start_date="2025-01-01",
                            end_date="2025-01-04",
                            initial_capital=100000,
                            short_window=2,
                            long_window=3,
                            max_positions=1,
                        ),
                    )
                )
                payload = app_module.visualize_boundary(
                    app_module.BoundaryVisualizationRequest(strategy_version_id=run["strategy_version_id"], top_k=1)
                )

            chart_path = Path(payload["boundary_chart_path"])
            text = chart_path.read_text(encoding="utf-8")
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            self.assertIn("<svg", text)
            self.assertIn("Boundary Distance", text)
            self.assertEqual(len(digest), 64)


if __name__ == "__main__":
    unittest.main()
