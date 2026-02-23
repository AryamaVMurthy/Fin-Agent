from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import duckdb

from fin_agent.code_strategy.runner import run_code_strategy_sandbox
from fin_agent.storage.paths import RuntimePaths
from fin_agent.viz.svg import write_line_chart_svg


def _to_date_key(value: Any) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value)


def _load_frame(
    paths: RuntimePaths,
    universe: list[str],
    end_date: str,
    lookback_days: int,
) -> list[dict[str, Any]]:
    if not universe:
        raise ValueError("universe must not be empty for live snapshot")
    placeholders = ",".join(["?"] * len(universe))
    sql = f"""
        SELECT symbol, CAST(timestamp AS DATE) AS day, close
        FROM market_ohlcv
        WHERE symbol IN ({placeholders})
          AND CAST(timestamp AS DATE) BETWEEN CAST(? AS DATE) - INTERVAL '{int(lookback_days)} days' AND CAST(? AS DATE)
        ORDER BY symbol, timestamp
    """
    with duckdb.connect(str(paths.duckdb_path)) as conn:
        rows = conn.execute(sql, [*universe, end_date, end_date]).fetchall()
    frame: list[dict[str, Any]] = []
    for symbol, day, close in rows:
        frame.append(
            {
                "symbol": str(symbol),
                "timestamp": _to_date_key(day),
                "close": float(close),
            }
        )
    return frame


def build_live_snapshot(
    paths: RuntimePaths,
    *,
    source_code: str,
    universe: list[str],
    end_date: str,
    lookback_days: int = 180,
    timeout_seconds: int = 5,
    memory_mb: int = 256,
    cpu_seconds: int = 2,
) -> list[dict[str, Any]]:
    frame = _load_frame(paths, universe=universe, end_date=end_date, lookback_days=lookback_days)
    if not frame:
        raise ValueError("no OHLCV rows available for live snapshot")

    sandbox = run_code_strategy_sandbox(
        paths=paths,
        source_code=source_code,
        timeout_seconds=timeout_seconds,
        memory_mb=memory_mb,
        cpu_seconds=cpu_seconds,
        data_bundle={"universe": universe},
        frame=frame,
        context={"mode": "live", "end_date": end_date},
    )
    outputs = sandbox.get("outputs", {})
    signal_rows = outputs.get("signals")
    if not isinstance(signal_rows, list):
        raise ValueError("strategy generate_signals must return list for live snapshot")

    latest_by_symbol: dict[str, tuple[str, float]] = {}
    for row in frame:
        symbol = str(row["symbol"])
        latest_by_symbol[symbol] = (str(row["timestamp"]), float(row["close"]))

    signal_by_symbol: dict[str, dict[str, Any]] = {}
    for item in signal_rows:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol", "")).strip()
        if symbol in latest_by_symbol and symbol not in signal_by_symbol:
            signal_by_symbol[symbol] = item

    snapshot: list[dict[str, Any]] = []
    for symbol in sorted(latest_by_symbol.keys()):
        date_value, close_value = latest_by_symbol[symbol]
        item = signal_by_symbol.get(symbol, {})
        action = str(item.get("signal", "watch")).strip().lower() or "watch"
        if action not in {"buy", "sell", "watch", "hold"}:
            action = "watch"
        reason_code = str(item.get("reason_code", f"signal_{action}")).strip() or f"signal_{action}"

        strength_raw = item.get("strength", 0.5)
        try:
            strength = float(strength_raw)
        except (TypeError, ValueError):
            strength = 0.5
        strength = max(0.0, min(1.0, strength))
        distance = 0.5 - strength
        abs_distance = abs(distance)

        snapshot.append(
            {
                "symbol": symbol,
                "date": date_value,
                "close": close_value,
                "action": action,
                "reason_code": reason_code,
                "score": round(abs_distance, 8),
                "signal_strength": strength,
                "distance_to_boundary": distance,
                "abs_distance_to_boundary": abs_distance,
                "similarity_basis": "distance_to_signal_decision_boundary",
                "signal_payload": item,
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
