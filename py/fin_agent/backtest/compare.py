from __future__ import annotations

from typing import Any

from fin_agent.storage import sqlite_store
from fin_agent.storage.paths import RuntimePaths


METRIC_KEYS = [
    "final_equity",
    "total_return",
    "cagr",
    "sharpe",
    "max_drawdown",
    "trade_count",
]


def _metric_deltas(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, float]:
    result: dict[str, float] = {}
    for key in METRIC_KEYS:
        left = float(baseline.get(key, 0.0))
        right = float(candidate.get(key, 0.0))
        result[key] = right - left
    return result


def _likely_causes(baseline_payload: dict[str, Any], candidate_payload: dict[str, Any], deltas: dict[str, float]) -> list[str]:
    notes: list[str] = []
    base_strategy = baseline_payload.get("strategy", {})
    cand_strategy = candidate_payload.get("strategy", {})

    for key in ("short_window", "long_window", "max_positions", "cost_bps", "signal_type"):
        if base_strategy.get(key) != cand_strategy.get(key):
            notes.append(
                f"strategy parameter changed: {key} baseline={base_strategy.get(key)} candidate={cand_strategy.get(key)}"
            )

    if deltas.get("total_return", 0.0) > 0:
        notes.append(f"candidate improved total_return by {deltas['total_return']:.6f}")
    elif deltas.get("total_return", 0.0) < 0:
        notes.append(f"candidate reduced total_return by {abs(deltas['total_return']):.6f}")

    if deltas.get("max_drawdown", 0.0) < 0:
        notes.append("candidate drawdown became deeper (more negative max_drawdown)")
    elif deltas.get("max_drawdown", 0.0) > 0:
        notes.append("candidate drawdown improved (less negative max_drawdown)")

    if deltas.get("trade_count", 0.0) != 0:
        notes.append(f"trade_count changed by {int(deltas['trade_count'])}")

    if not notes:
        notes.append("no clear cause identified from available metadata")
    return notes


def compare_backtest_runs(
    runtime_paths: RuntimePaths,
    baseline_run_id: str,
    candidate_run_id: str,
) -> dict[str, Any]:
    baseline = sqlite_store.get_backtest_run(runtime_paths, baseline_run_id)
    candidate = sqlite_store.get_backtest_run(runtime_paths, candidate_run_id)

    baseline_metrics = baseline["metrics"]
    candidate_metrics = candidate["metrics"]
    deltas = _metric_deltas(baseline_metrics, candidate_metrics)
    causes = _likely_causes(baseline["payload"], candidate["payload"], deltas)

    return {
        "baseline": {
            "run_id": baseline["run_id"],
            "created_at": baseline["created_at"],
            "metrics": baseline_metrics,
        },
        "candidate": {
            "run_id": candidate["run_id"],
            "created_at": candidate["created_at"],
            "metrics": candidate_metrics,
        },
        "metrics_delta": deltas,
        "artifact_links": {
            "baseline": baseline["artifacts"],
            "candidate": candidate["artifacts"],
        },
        "likely_causes": causes,
    }
