from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import duckdb

from fin_agent.storage.paths import RuntimePaths
from fin_agent.strategy.models import StrategySpec
from fin_agent.viz.svg import write_line_chart_svg


def _moving_average(values: list[float], window: int) -> float:
    if window <= 0:
        raise ValueError("window must be positive")
    if len(values) < window:
        return float("nan")
    segment = values[-window:]
    return sum(segment) / float(window)


def _load_symbol_closes(paths: RuntimePaths, symbol: str, end_date: str) -> list[tuple[str, float]]:
    with duckdb.connect(str(paths.duckdb_path)) as conn:
        rows = conn.execute(
            """
            SELECT CAST(timestamp AS DATE) AS day, close
            FROM market_ohlcv
            WHERE symbol = ?
              AND CAST(timestamp AS DATE) <= CAST(? AS DATE)
            ORDER BY timestamp
            """,
            [symbol, end_date],
        ).fetchall()
    return [(str(day), float(close)) for day, close in rows]


def build_live_snapshot(paths: RuntimePaths, strategy: StrategySpec) -> list[dict[str, Any]]:
    boundary_threshold = 0.0025
    snapshot: list[dict[str, Any]] = []
    for symbol in sorted(strategy.universe):
        points = _load_symbol_closes(paths, symbol, strategy.end_date)
        if not points:
            continue
        dates = [row[0] for row in points]
        closes = [row[1] for row in points]
        short_ma = _moving_average(closes, strategy.short_window)
        long_ma = _moving_average(closes, strategy.long_window)
        if math.isnan(short_ma) or math.isnan(long_ma):
            continue

        latest_close = closes[-1]
        distance = 0.0 if latest_close == 0 else (short_ma - long_ma) / latest_close
        abs_distance = abs(distance)

        if abs_distance <= boundary_threshold:
            action = "watch"
            reason = "near_crossover_boundary"
        elif distance > 0:
            action = "buy"
            reason = "trend_above_crossover"
        else:
            action = "sell"
            reason = "trend_below_crossover"

        snapshot.append(
            {
                "symbol": symbol,
                "date": dates[-1],
                "close": latest_close,
                "short_ma": short_ma,
                "long_ma": long_ma,
                "distance_to_boundary": distance,
                "abs_distance_to_boundary": abs_distance,
                "action": action,
                "reason_code": reason,
                "score": round(abs_distance, 8),
                "similarity_basis": "distance_to_sma_crossover_boundary",
            }
        )
    return snapshot


def boundary_candidates(snapshot: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    ordered = sorted(
        snapshot,
        key=lambda row: (
            float(row["abs_distance_to_boundary"]),
            str(row["symbol"]),
        ),
    )
    return ordered[:top_k]


def write_boundary_chart(
    paths: RuntimePaths,
    strategy_version_id: str,
    candidates: list[dict[str, Any]],
) -> str:
    path = paths.artifacts_dir / "boundary"
    path.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    chart_path = path / f"boundary-{strategy_version_id}-{now}.svg"
    labels = [row["symbol"] for row in candidates]
    values = [float(row["distance_to_boundary"]) for row in candidates]
    write_line_chart_svg(
        chart_path,
        f"Boundary Distance - {strategy_version_id}",
        labels,
        values,
    )
    return str(chart_path)
