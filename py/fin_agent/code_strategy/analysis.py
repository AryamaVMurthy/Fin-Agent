from __future__ import annotations

from typing import Any

from fin_agent.storage import sqlite_store
from fin_agent.storage.paths import RuntimePaths


def _strategy_has_sell_path(source_code: str) -> bool:
    return "\"sell\"" in source_code.lower() or "'sell'" in source_code.lower()


def analyze_code_strategy_run(
    paths: RuntimePaths,
    run_id: str,
    source_code: str,
    max_suggestions: int = 5,
) -> dict[str, Any]:
    if max_suggestions <= 0:
        raise ValueError("max_suggestions must be positive")
    if not source_code.strip():
        raise ValueError("source_code is required")

    run = sqlite_store.get_backtest_run(paths, run_id)
    payload = run.get("payload", {})
    if payload.get("mode") != "code_strategy":
        raise ValueError(f"run_id={run_id} is not a code_strategy backtest run")

    metrics = run.get("metrics", {})
    suggestions: list[dict[str, Any]] = []

    max_drawdown = float(metrics.get("max_drawdown", 0.0))
    sharpe = float(metrics.get("sharpe", 0.0))
    trade_count = int(metrics.get("trade_count", 0))
    has_sell = _strategy_has_sell_path(source_code)

    if max_drawdown < -0.1:
        suggestions.append(
            {
                "title": "Add drawdown stop guardrail",
                "evidence": f"run max_drawdown={max_drawdown:.6f}",
                "expected_impact": "Reduce tail losses and improve drawdown stability.",
                "confidence": 0.8,
                "patch": (
                    "def risk_rules(positions, context):\n"
                    "    return {\"max_positions\": 1, \"max_drawdown_stop\": 0.08}"
                ),
            }
        )

    if trade_count <= 2:
        suggestions.append(
            {
                "title": "Increase signal opportunities",
                "evidence": f"run trade_count={trade_count}",
                "expected_impact": "Increase sample size so metrics are less noisy.",
                "confidence": 0.7,
                "patch": (
                    "def generate_signals(frame, state, context):\n"
                    "    # add threshold/exit conditions to avoid single-trade behavior\n"
                    "    ...\n"
                ),
            }
        )

    if not has_sell:
        suggestions.append(
            {
                "title": "Add explicit sell path",
                "evidence": "generate_signals source has no explicit 'sell' output",
                "expected_impact": "Improve risk control and reduce holding-time drift.",
                "confidence": 0.86,
                "patch": (
                    "if trend_reversal:\n"
                    "    signals.append({\"symbol\": symbol, \"signal\": \"sell\", \"strength\": 0.7})"
                ),
            }
        )

    if sharpe < 1.0:
        suggestions.append(
            {
                "title": "Add noise filter around entry threshold",
                "evidence": f"run sharpe={sharpe:.6f}",
                "expected_impact": "Reduce whipsaw trades and improve risk-adjusted return.",
                "confidence": 0.72,
                "patch": (
                    "if momentum > entry_threshold and volatility < vol_cap:\n"
                    "    signals.append({\"symbol\": symbol, \"signal\": \"buy\", \"strength\": 0.8})"
                ),
            }
        )

    if not suggestions:
        suggestions.append(
            {
                "title": "Add parameterization hooks",
                "evidence": "no critical failure detected, but strategy is not parameterized for tuning",
                "expected_impact": "Makes future tuning and scenario analysis easier.",
                "confidence": 0.55,
                "patch": (
                    "lookback = int(context.get('lookback', 20))\n"
                    "threshold = float(context.get('threshold', 0.0))"
                ),
            }
        )

    trimmed = suggestions[:max_suggestions]
    return {
        "run_id": run_id,
        "metrics": metrics,
        "suggestions": trimmed,
        "suggestion_count": len(trimmed),
        "mode": "patch_suggestions_only",
        "auto_apply": False,
    }
