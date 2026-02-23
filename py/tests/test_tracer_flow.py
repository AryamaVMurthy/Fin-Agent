import tempfile
import unittest
from pathlib import Path


class TracerFlowTests(unittest.TestCase):
    def test_code_strategy_backtest_produces_metrics(self) -> None:
        from fin_agent.code_strategy.backtest import run_code_strategy_backtest
        from fin_agent.data.importer import import_ohlcv_file
        from fin_agent.storage.paths import RuntimePaths

        strategy_code = """
def prepare(data_bundle, context):
    return {"symbols": data_bundle.get("universe", [])}

def generate_signals(frame, state, context):
    symbols = state.get("symbols", [])
    if not symbols:
        return []
    return [{"symbol": symbols[0], "signal": "buy", "strength": 0.8, "reason_code": "signal_buy"}]

def risk_rules(positions, context):
    return {"max_positions": 1}
"""

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            csv_path = root / "prices.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "timestamp,symbol,open,high,low,close,volume",
                        "2025-01-01T00:00:00Z,ABC,100,101,99,100,1000",
                        "2025-01-02T00:00:00Z,ABC,100,102,99,101,1100",
                        "2025-01-03T00:00:00Z,ABC,101,104,100,103,1200",
                        "2025-01-04T00:00:00Z,ABC,103,105,102,104,1200",
                        "2025-01-05T00:00:00Z,ABC,104,106,103,105,1300",
                        "2025-01-06T00:00:00Z,ABC,105,107,104,106,1300",
                        "2025-01-07T00:00:00Z,ABC,106,106,100,101,1400",
                        "2025-01-08T00:00:00Z,ABC,101,103,99,100,1400",
                        "2025-01-09T00:00:00Z,ABC,100,102,98,99,1500",
                        "2025-01-10T00:00:00Z,ABC,99,101,97,98,1500",
                    ]
                ),
                encoding="utf-8",
            )
            paths = RuntimePaths(root=root)
            import_ohlcv_file(csv_path, paths)
            run = run_code_strategy_backtest(
                paths=paths,
                strategy_name="Code Tracer",
                source_code=strategy_code,
                universe=["ABC"],
                start_date="2025-01-01",
                end_date="2025-01-10",
                initial_capital=100000.0,
            )

            self.assertEqual(run["strategy_name"], "Code Tracer")
            self.assertGreater(float(run["metrics"]["final_equity"]), 0)
            self.assertTrue(run["artifacts"]["equity_curve_path"])
            self.assertTrue(run["artifacts"]["drawdown_path"])


if __name__ == "__main__":
    unittest.main()
