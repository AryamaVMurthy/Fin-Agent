from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fin_agent.tax.india import IndiaTaxAssumptions, compute_tax_report


class TaxOverlayExtendedTests(unittest.TestCase):
    def test_ltcg_exemption_and_cess_applied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "trade_blotter.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "symbol,entry_ts,exit_ts,entry_price,exit_price,pnl,reason_code",
                        "ABC,2024-01-01,2025-06-01,100,200,200000,rule_exit",
                    ]
                ),
                encoding="utf-8",
            )
            report = compute_tax_report(
                trade_blotter_path=str(csv_path),
                strategy_payload={"initial_capital": 200000, "max_positions": 1},
                assumptions=IndiaTaxAssumptions(
                    ltcg_rate=0.125,
                    ltcg_exemption_amount=125000.0,
                    apply_cess=True,
                    cess_rate=0.04,
                ),
            )
        self.assertGreater(report["tax_breakdown"]["ltcg_tax"], 0.0)
        self.assertGreater(report["tax_breakdown"]["cess"], 0.0)
        self.assertLess(report["metrics_post_tax"]["net_profit_after_tax"], report["metrics_pre_tax"]["gross_profit"])


if __name__ == "__main__":
    unittest.main()
