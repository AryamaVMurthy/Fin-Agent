from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fin_agent.verification.ui_dashboard import generate_rigorous_ui_dashboard


class RigorousUIDashboardTests(unittest.TestCase):
    def _write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def test_generates_responsive_mobile_table_markup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            run_dir = root / ".finagent" / "verification" / "rigorous-20260223T000000Z"
            artifacts = run_dir / "artifacts"
            http_dir = artifacts / "http"
            summary_path = artifacts / "summary.json"

            equity = root / ".finagent" / "artifacts" / "runs" / "equity.svg"
            drawdown = root / ".finagent" / "artifacts" / "runs" / "drawdown.svg"
            boundary = root / ".finagent" / "artifacts" / "boundary" / "boundary.svg"
            trade_csv = root / ".finagent" / "artifacts" / "runs" / "trades.csv"
            signal_csv = root / ".finagent" / "artifacts" / "runs" / "signals.csv"
            for path in [equity, drawdown, boundary, trade_csv, signal_csv]:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("ok", encoding="utf-8")

            self._write_json(
                summary_path,
                {
                    "status": "passed",
                    "generated_at": "2026-02-23T00:00:00+00:00",
                    "api_base": "http://127.0.0.1:18080",
                    "wrapper_base": "http://127.0.0.1:18090",
                    "steps": [],
                },
            )
            self._write_json(
                http_dir / "014-backtest-run-b.json",
                {
                    "response": {
                        "strategy_version_id": "sv-1",
                        "metrics": {
                            "final_equity": 1000.0,
                            "sharpe": 1.2,
                            "max_drawdown": -0.1,
                            "cagr": 0.2,
                            "trade_count": 5,
                        },
                        "artifacts": {
                            "equity_curve_path": str(equity),
                            "drawdown_path": str(drawdown),
                            "trade_blotter_path": str(trade_csv),
                            "signal_context_path": str(signal_csv),
                        },
                    }
                },
            )
            self._write_json(
                http_dir / "018-tuning-run.json",
                {
                    "response": {
                        "best_candidate": {"score": 1.55},
                        "sensitivity_analysis": {
                            "short_window": {
                                "status": "ok",
                                "baseline_value": 5,
                                "alternative_value": 8,
                                "score_delta": 0.12,
                            }
                        },
                    }
                },
            )
            self._write_json(
                http_dir / "019-analysis-deep-dive.json",
                {
                    "response": {
                        "suggestions": [
                            {
                                "title": "Improve exits",
                                "evidence": "low hit-rate",
                                "confidence": 0.66,
                                "expected_impact": "Improve risk adjusted return",
                            }
                        ]
                    }
                },
            )
            self._write_json(
                http_dir / "020-visualize-trade-blotter.json",
                {
                    "response": {
                        "artifacts": {
                            "trade_blotter_path": str(trade_csv),
                            "signal_context_path": str(signal_csv),
                        },
                        "trades": [
                            {
                                "symbol": "ABC",
                                "entry_ts": "2025-01-01",
                                "entry_price": "100",
                                "exit_ts": "2025-01-02",
                                "exit_price": "101",
                                "pnl": "10",
                                "entry_reason": "cross",
                                "exit_reason": "stop",
                            }
                        ],
                    }
                },
            )
            self._write_json(
                http_dir / "024-visualize-boundary.json",
                {
                    "response": {
                        "boundary_chart_path": str(boundary),
                    }
                },
            )

            payload = generate_rigorous_ui_dashboard(run_dir=run_dir, workspace_root=root)

            dashboard = Path(payload["paths"]["dashboard"])
            html = dashboard.read_text(encoding="utf-8")
            self.assertIn('class="responsive-table"', html)
            self.assertIn('data-label="Expected Impact"', html)
            self.assertIn("@media (max-width: 760px)", html)
            self.assertIn("td::before", html)

    def test_missing_required_artifact_errors_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            run_dir = root / ".finagent" / "verification" / "rigorous-20260223T000000Z"
            artifacts = run_dir / "artifacts"
            http_dir = artifacts / "http"
            self._write_json(
                artifacts / "summary.json",
                {
                    "status": "passed",
                    "generated_at": "2026-02-23T00:00:00+00:00",
                    "api_base": "http://127.0.0.1:18080",
                    "wrapper_base": "http://127.0.0.1:18090",
                    "steps": [],
                },
            )
            self._write_json(http_dir / "014-backtest-run-b.json", {"response": {}})

            with self.assertRaisesRegex(ValueError, "missing required HTTP artifact"):
                generate_rigorous_ui_dashboard(run_dir=run_dir, workspace_root=root)


if __name__ == "__main__":
    unittest.main()
