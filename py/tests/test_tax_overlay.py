from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fin_agent.api import app as app_module
from fin_agent.storage.paths import RuntimePaths


VALID_CODE = """
def prepare(data_bundle, context):
    return {"prepared": True}

def generate_signals(frame, state, context):
    return [{"symbol": "ABC", "signal": "buy", "strength": 0.59, "reason_code": "signal_buy_tax"}]

def risk_rules(positions, context):
    return {"max_positions": 1}
"""


class TaxOverlayTests(unittest.TestCase):
    def test_tax_report_endpoint_returns_pre_and_post_tax(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            paths = RuntimePaths(root=root / ".finagent")

            csv_path = root / "prices.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "timestamp,symbol,open,high,low,close,volume",
                        "2025-01-01T00:00:00Z,ABC,100,101,99,100,1000",
                        "2025-01-02T00:00:00Z,ABC,100,103,99,102,1100",
                        "2025-01-03T00:00:00Z,ABC,102,104,101,103,1200",
                        "2025-01-04T00:00:00Z,ABC,103,106,102,105,1200",
                        "2025-01-05T00:00:00Z,ABC,105,107,104,106,1300",
                        "2025-01-06T00:00:00Z,ABC,106,108,102,103,1300",
                        "2025-01-07T00:00:00Z,ABC,103,104,99,100,1400",
                        "2025-01-08T00:00:00Z,ABC,100,101,97,98,1400",
                    ]
                ),
                encoding="utf-8",
            )

            from unittest.mock import patch

            with patch.object(app_module, "_runtime_paths", return_value=paths):
                app_module.import_data(app_module.ImportRequest(path=str(csv_path)))
                run = app_module.code_strategy_backtest(
                    app_module.CodeStrategyBacktestRequest(
                        strategy_name="Tax Test",
                        source_code=VALID_CODE,
                        universe=["ABC"],
                        start_date="2025-01-01",
                        end_date="2025-01-08",
                        initial_capital=100000.0,
                    )
                )
                report = app_module.backtest_tax_report(
                    app_module.BacktestTaxReportRequest(run_id=run["run_id"], enabled=True)
                )

            self.assertIn("metrics_pre_tax", report)
            self.assertIn("metrics_post_tax", report)
            self.assertIn("tax_breakdown", report)
            self.assertLessEqual(report["metrics_post_tax"]["net_profit_after_tax"], report["metrics_pre_tax"]["gross_profit"])


if __name__ == "__main__":
    unittest.main()
