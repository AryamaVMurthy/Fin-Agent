from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from fin_agent.api import app as app_module
from fin_agent.storage.paths import RuntimePaths


VALID_CODE = """
def prepare(data_bundle, context):
    return {"prepared": True}

def generate_signals(frame, state, context):
    return [{"symbol": "ABC", "signal": "buy", "strength": 0.63, "reason_code": "signal_buy_visual"}]

def risk_rules(positions, context):
    return {"max_positions": 1}
"""


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
                run = app_module.code_strategy_backtest(
                    app_module.CodeStrategyBacktestRequest(
                        strategy_name="Visual",
                        source_code=VALID_CODE,
                        universe=["ABC"],
                        start_date="2025-01-01",
                        end_date="2025-01-04",
                        initial_capital=100000.0,
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
