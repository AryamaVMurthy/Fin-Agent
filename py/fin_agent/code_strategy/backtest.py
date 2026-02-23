from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

from fin_agent.backtest.models import BacktestArtifacts, BacktestRun
from fin_agent.backtest.runner import _compute_metrics
from fin_agent.code_strategy.runner import run_code_strategy_sandbox
from fin_agent.code_strategy.validator import validate_code_strategy_source
from fin_agent.storage import sqlite_store
from fin_agent.storage.paths import RuntimePaths
from fin_agent.viz.svg import write_line_chart_svg
from fin_agent.world_state.service import build_world_state_manifest


def _date_key(value: datetime) -> str:
    return value.strftime("%Y-%m-%d")


def run_code_strategy_backtest(
    paths: RuntimePaths,
    strategy_name: str,
    source_code: str,
    universe: list[str],
    start_date: str,
    end_date: str,
    initial_capital: float,
    timeout_seconds: int = 5,
    memory_mb: int = 256,
    cpu_seconds: int = 2,
) -> dict[str, Any]:
    if not universe:
        raise ValueError("universe must not be empty")
    if initial_capital <= 0:
        raise ValueError("initial_capital must be positive")

    validation = validate_code_strategy_source(source_code)
    code_version = sqlite_store.save_code_strategy_version(
        paths,
        strategy_name=strategy_name,
        source_code=source_code,
        validation=validation,
    )

    placeholders = ",".join(["?"] * len(universe))
    sql = f"""
        SELECT symbol, timestamp, close
        FROM market_ohlcv
        WHERE symbol IN ({placeholders})
          AND CAST(timestamp AS DATE) BETWEEN CAST(? AS DATE) AND CAST(? AS DATE)
        ORDER BY symbol, timestamp
    """
    with duckdb.connect(str(paths.duckdb_path)) as conn:
        rows = conn.execute(sql, [*universe, start_date, end_date]).fetchall()
    if not rows:
        raise ValueError("no OHLCV rows found for requested universe/date range")

    frame: list[dict[str, Any]] = []
    by_symbol: dict[str, list[tuple[str, float]]] = defaultdict(list)
    all_dates: set[str] = set()
    for symbol, ts, close in rows:
        date_key = _date_key(ts)
        frame.append({"symbol": str(symbol), "timestamp": date_key, "close": float(close)})
        by_symbol[str(symbol)].append((date_key, float(close)))
        all_dates.add(date_key)

    sandbox = run_code_strategy_sandbox(
        paths,
        source_code=source_code,
        timeout_seconds=timeout_seconds,
        memory_mb=memory_mb,
        cpu_seconds=cpu_seconds,
        data_bundle={"universe": universe},
        frame=frame,
        context={"start_date": start_date, "end_date": end_date, "initial_capital": initial_capital},
    )

    outputs = sandbox["outputs"]
    signals = outputs.get("signals", [])
    active_symbols = {
        str(item.get("symbol"))
        for item in signals
        if isinstance(item, dict) and str(item.get("signal", "")).lower() == "buy" and str(item.get("symbol")) in by_symbol
    }
    ordered_dates = sorted(all_dates)
    if len(ordered_dates) < 2:
        raise ValueError("need at least two dates for code strategy backtest")

    equity_series: list[float] = []
    if not active_symbols:
        equity_series = [initial_capital for _ in ordered_dates]
        trade_count = 0
    else:
        allocation = initial_capital / float(len(active_symbols))
        trade_count = len(active_symbols) * 2
        last_close_by_symbol: dict[str, float] = {}
        symbol_points: dict[str, dict[str, float]] = {
            symbol: {day: close for day, close in points} for symbol, points in by_symbol.items()
        }
        first_close_by_symbol: dict[str, float] = {
            symbol: by_symbol[symbol][0][1] for symbol in active_symbols
        }
        for day in ordered_dates:
            total = 0.0
            for symbol in active_symbols:
                if day in symbol_points[symbol]:
                    last_close_by_symbol[symbol] = symbol_points[symbol][day]
                close = last_close_by_symbol.get(symbol, first_close_by_symbol[symbol])
                total += allocation * (close / first_close_by_symbol[symbol])
            equity_series.append(total)

    metrics = _compute_metrics(equity_series, trade_count=trade_count)
    drawdowns: list[float] = []
    peak = equity_series[0]
    for value in equity_series:
        peak = max(peak, value)
        drawdowns.append((value / peak) - 1.0)

    run_dir = paths.artifacts_dir / "code-backtests"
    run_dir.mkdir(parents=True, exist_ok=True)
    temp_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    equity_path = run_dir / f"equity-{temp_id}.svg"
    drawdown_path = run_dir / f"drawdown-{temp_id}.svg"
    write_line_chart_svg(equity_path, f"Code Strategy Equity - {strategy_name}", ordered_dates, equity_series)
    write_line_chart_svg(drawdown_path, f"Code Strategy Drawdown - {strategy_name}", ordered_dates, drawdowns)

    manifest = build_world_state_manifest(paths, universe, start_date, end_date)
    run_id = sqlite_store.save_backtest_run(
        paths,
        strategy_version_id=code_version["strategy_version_id"],
        world_manifest_id=manifest.manifest_id,
        metrics=metrics.__dict__,
        artifacts={"equity_curve_path": str(equity_path), "drawdown_path": str(drawdown_path)},
        payload={
            "mode": "code_strategy",
            "strategy_name": strategy_name,
            "universe": universe,
            "signals": signals,
            "sandbox_run_id": sandbox["run_id"],
        },
    )
    sqlite_store.append_audit_event(
        paths,
        "code.backtest.run",
        {
            "run_id": run_id,
            "strategy_name": strategy_name,
            "strategy_version_id": code_version["strategy_version_id"],
            "signals_count": len(signals) if isinstance(signals, list) else 0,
            "sandbox_run_id": sandbox["run_id"],
            "metrics": metrics.__dict__,
        },
    )

    run = BacktestRun(
        run_id=run_id,
        strategy_name=strategy_name,
        strategy_version_id=code_version["strategy_version_id"],
        world_manifest_id=manifest.manifest_id,
        metrics=metrics,
        artifacts=BacktestArtifacts(equity_curve_path=str(equity_path), drawdown_path=str(drawdown_path)),
    )
    return {
        "run_id": run.run_id,
        "strategy_name": run.strategy_name,
        "strategy_version_id": run.strategy_version_id,
        "world_manifest_id": run.world_manifest_id,
        "metrics": run.metrics.__dict__,
        "artifacts": run.artifacts.__dict__,
        "sandbox_run_id": sandbox["run_id"],
        "signals_count": len(signals) if isinstance(signals, list) else 0,
    }
