from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fin_agent.api import app as app_module
from fin_agent.storage.paths import RuntimePaths


class ScreenerApiTests(unittest.TestCase):
    def _seed_prices(self, root: Path) -> Path:
        csv_path = root / "prices.csv"
        csv_path.write_text(
            "\n".join(
                [
                    "timestamp,symbol,open,high,low,close,volume",
                    "2026-02-17T00:00:00Z,INFY,100,102,99,101,100000",
                    "2026-02-18T00:00:00Z,INFY,101,104,100,103,110000",
                    "2026-02-19T00:00:00Z,INFY,103,105,102,104,120000",
                    "2026-02-17T00:00:00Z,TCS,200,202,198,199,80000",
                    "2026-02-18T00:00:00Z,TCS,199,201,197,198,85000",
                    "2026-02-19T00:00:00Z,TCS,198,200,196,197,90000",
                ]
            ),
            encoding="utf-8",
        )
        return csv_path

    def test_formula_validate_and_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            paths = RuntimePaths(root=root / ".finagent")
            csv_path = self._seed_prices(root)

            with patch.object(app_module, "_runtime_paths", return_value=paths):
                import_payload = app_module.import_data(app_module.ImportRequest(path=str(csv_path)))
                self.assertGreater(import_payload["rows_inserted"], 0)

                validate = app_module.screener_formula_validate(
                    app_module.ScreenerFormulaValidateRequest(formula="close > open and volume >= 90000")
                )
                self.assertTrue(validate["valid"])

                app_module.technicals_compute(
                    app_module.TechnicalsRequest(
                        universe=["INFY", "TCS"],
                        start_date="2026-02-17",
                        end_date="2026-02-19",
                        short_window=2,
                        long_window=3,
                    )
                )

                derived = app_module.screener_formula_validate(
                    app_module.ScreenerFormulaValidateRequest(formula="sma_gap_pct > -10 and return_1d_pct > -5")
                )
                self.assertTrue(derived["valid"])

                out = app_module.screener_run(
                    app_module.ScreenerRunRequest(
                        formula="volume >= 90000 and return_1d_pct > -1000",
                        as_of="2026-02-19",
                        universe=["INFY", "TCS"],
                        top_k=10,
                        rank_by="return_1d_pct",
                        sort_order="desc",
                    )
                )
                self.assertGreaterEqual(out["count"], 1)
                self.assertEqual(out["rank_by"], "return_1d_pct")
                self.assertEqual(out["sort_order"], "desc")
                symbols = {row["symbol"] for row in out["rows"]}
                self.assertIn("INFY", symbols)
                self.assertIn("TCS", symbols)
                self.assertEqual(out["rows"][0]["symbol"], "INFY")


if __name__ == "__main__":
    unittest.main()
