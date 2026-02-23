from __future__ import annotations

import duckdb

from fin_agent.storage.paths import RuntimePaths
from fin_agent.strategy.models import IntentSnapshot


def _count_market_rows(paths: RuntimePaths, universe: list[str], start_date: str, end_date: str) -> int:
    if not universe:
        raise ValueError("preflight failed: universe must not be empty")
    placeholders = ",".join(["?"] * len(universe))
    sql = f"""
        SELECT COUNT(*) AS row_count
        FROM market_ohlcv
        WHERE symbol IN ({placeholders})
          AND CAST(timestamp AS DATE) BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
    """
    with duckdb.connect(str(paths.duckdb_path)) as conn:
        row_count = int(conn.execute(sql, [*universe, start_date, end_date]).fetchone()[0])
    if row_count <= 0:
        raise ValueError("preflight failed: no rows available for requested range")
    return row_count


def estimate_backtest_runtime_seconds(paths: RuntimePaths, intent: IntentSnapshot) -> float:
    row_count = _count_market_rows(paths, intent.universe, intent.start_date, intent.end_date)
    return row_count * 0.0002


def estimate_world_state_runtime_seconds(
    paths: RuntimePaths, universe: list[str], start_date: str, end_date: str
) -> float:
    row_count = _count_market_rows(paths, universe, start_date, end_date)
    return (row_count * 0.0001) + (len(universe) * 0.01)


def estimate_tuning_runtime_seconds(num_trials: int, per_trial_estimated_seconds: float) -> float:
    if num_trials <= 0:
        raise ValueError("preflight failed: num_trials must be positive")
    if per_trial_estimated_seconds <= 0:
        raise ValueError("preflight failed: per_trial_estimated_seconds must be positive")
    return float(num_trials) * float(per_trial_estimated_seconds)


def estimate_custom_code_runtime_seconds(
    paths: RuntimePaths,
    universe: list[str],
    start_date: str,
    end_date: str,
    complexity_multiplier: float,
) -> float:
    if complexity_multiplier <= 0:
        raise ValueError("preflight failed: complexity_multiplier must be positive")
    row_count = _count_market_rows(paths, universe, start_date, end_date)
    return row_count * 0.00035 * complexity_multiplier


def enforce_world_state_budget(
    paths: RuntimePaths,
    universe: list[str],
    start_date: str,
    end_date: str,
    max_estimated_seconds: float,
) -> dict[str, float]:
    if max_estimated_seconds <= 0:
        raise ValueError("max_estimated_seconds must be positive")
    estimate_seconds = estimate_world_state_runtime_seconds(paths, universe, start_date, end_date)
    if estimate_seconds > max_estimated_seconds:
        raise ValueError(
            f"preflight budget exceeded: estimated_seconds={estimate_seconds:.2f}, "
            f"max_allowed_seconds={max_estimated_seconds:.2f}. "
            "Reduce universe size/date range before world-state build."
        )
    return {
        "estimated_seconds": estimate_seconds,
        "max_allowed_seconds": max_estimated_seconds,
    }


def enforce_tuning_budget(num_trials: int, per_trial_estimated_seconds: float, max_estimated_seconds: float) -> dict[str, float]:
    if max_estimated_seconds <= 0:
        raise ValueError("max_estimated_seconds must be positive")
    estimate_seconds = estimate_tuning_runtime_seconds(num_trials, per_trial_estimated_seconds)
    if estimate_seconds > max_estimated_seconds:
        raise ValueError(
            f"preflight budget exceeded: estimated_seconds={estimate_seconds:.2f}, "
            f"max_allowed_seconds={max_estimated_seconds:.2f}. "
            "Reduce num_trials or per-trial compute complexity."
        )
    return {
        "estimated_seconds": estimate_seconds,
        "max_allowed_seconds": max_estimated_seconds,
    }


def enforce_custom_code_budget(
    paths: RuntimePaths,
    universe: list[str],
    start_date: str,
    end_date: str,
    complexity_multiplier: float,
    max_estimated_seconds: float,
) -> dict[str, float]:
    if max_estimated_seconds <= 0:
        raise ValueError("max_estimated_seconds must be positive")
    estimate_seconds = estimate_custom_code_runtime_seconds(
        paths,
        universe,
        start_date,
        end_date,
        complexity_multiplier,
    )
    if estimate_seconds > max_estimated_seconds:
        raise ValueError(
            f"preflight budget exceeded: estimated_seconds={estimate_seconds:.2f}, "
            f"max_allowed_seconds={max_estimated_seconds:.2f}. "
            "Reduce date range, universe size, or code complexity."
        )
    return {
        "estimated_seconds": estimate_seconds,
        "max_allowed_seconds": max_estimated_seconds,
    }


def enforce_backtest_budget(paths: RuntimePaths, intent: IntentSnapshot, max_estimated_seconds: float) -> dict[str, float]:
    if max_estimated_seconds <= 0:
        raise ValueError("max_estimated_seconds must be positive")
    estimate_seconds = estimate_backtest_runtime_seconds(paths, intent)
    if estimate_seconds > max_estimated_seconds:
        raise ValueError(
            f"preflight budget exceeded: estimated_seconds={estimate_seconds:.2f}, "
            f"max_allowed_seconds={max_estimated_seconds:.2f}. "
            "Reduce universe size, shorten date range, or increase granularity."
        )
    return {
        "estimated_seconds": estimate_seconds,
        "max_allowed_seconds": max_estimated_seconds,
    }
