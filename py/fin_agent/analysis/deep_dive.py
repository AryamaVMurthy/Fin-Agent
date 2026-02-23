from __future__ import annotations

from datetime import date
from typing import Any

from fin_agent.storage import sqlite_store
from fin_agent.storage.paths import RuntimePaths


def _trading_days_between(start_date: str, end_date: str) -> int:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if end < start:
        raise ValueError("end_date must be on or after start_date")
    return max((end - start).days + 1, 1)


def analyze_backtest_run(paths: RuntimePaths, run_id: str) -> dict[str, Any]:
    run = sqlite_store.get_backtest_run(paths, run_id)
    metrics = run.get("metrics", {})
    payload = run.get("payload", {})
    strategy = payload.get("strategy", {})

    start_date = str(strategy.get("start_date", "1970-01-01"))
    end_date = str(strategy.get("end_date", "1970-01-01"))
    trade_count = int(metrics.get("trade_count", 0))
    days = _trading_days_between(start_date, end_date)
    turnover_per_year = float(trade_count) / float(days) * 252.0

    universe_size = len(strategy.get("universe", [])) if isinstance(strategy.get("universe", []), list) else 0
    max_positions = int(strategy.get("max_positions", 1) or 1)
    exposure_ratio = 0.0 if max_positions <= 0 else min(1.0, float(universe_size) / float(max_positions))

    diagnostics = {
        "risk": {
            "max_drawdown": float(metrics.get("max_drawdown", 0.0)),
            "sharpe": float(metrics.get("sharpe", 0.0)),
            "cagr": float(metrics.get("cagr", 0.0)),
        },
        "exposure": {
            "universe_size": universe_size,
            "max_positions": max_positions,
            "exposure_ratio": exposure_ratio,
        },
        "trade": {
            "trade_count": trade_count,
            "turnover_per_year_est": turnover_per_year,
        },
    }

    suggestions: list[dict[str, Any]] = []
    max_drawdown = float(metrics.get("max_drawdown", 0.0))
    sharpe = float(metrics.get("sharpe", 0.0))
    long_window = int(strategy.get("long_window", 0) or 0)
    short_window = int(strategy.get("short_window", 0) or 0)

    if max_drawdown < -0.15:
        suggestions.append(
            {
                "title": "Reduce downside concentration",
                "evidence": f"max_drawdown={max_drawdown:.6f}",
                "expected_impact": "Lower peak-to-trough loss at cost of some upside.",
                "confidence": 0.82,
                "actionable_change": "Tighten risk rules or reduce max_positions/capital at risk.",
            }
        )

    if sharpe < 1.0:
        suggestions.append(
            {
                "title": "Improve signal quality filter",
                "evidence": f"sharpe={sharpe:.6f}",
                "expected_impact": "Increase risk-adjusted returns by reducing noisy entries.",
                "confidence": 0.75,
                "actionable_change": "Add confirmation filters and re-test with tighter entry thresholds.",
            }
        )

    if trade_count <= 4:
        suggestions.append(
            {
                "title": "Increase trade opportunity density",
                "evidence": f"trade_count={trade_count}",
                "expected_impact": "Provide better statistical confidence in backtest metrics.",
                "confidence": 0.68,
                "actionable_change": (
                    f"Try smaller windows (short_window<{short_window or 5}, long_window<{long_window or 20})."
                ),
            }
        )

    if trade_count >= 120:
        suggestions.append(
            {
                "title": "Control over-trading",
                "evidence": f"turnover_per_year_est={turnover_per_year:.2f}",
                "expected_impact": "Reduce transaction costs and signal churn.",
                "confidence": 0.7,
                "actionable_change": "Widen signal threshold or enforce a minimum holding period.",
            }
        )

    if not suggestions:
        suggestions.append(
            {
                "title": "Run robustness checks",
                "evidence": "core metrics are stable but robustness diagnostics are not yet exhausted",
                "expected_impact": "Improve confidence under regime shifts.",
                "confidence": 0.55,
                "actionable_change": "Run walk-forward windows and compare out-of-sample periods.",
            }
        )

    return {
        "run_id": run_id,
        "metrics": metrics,
        "diagnostics": diagnostics,
        "suggestions": suggestions,
        "suggestion_count": len(suggestions),
    }
